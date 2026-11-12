"""One bounded, credential-redacted FTP upload attempt with persisted backoff.

Run locally only. This script and the credentials file are not server payloads.
An uploaded status means transfer and SIZE checks passed; remote SHA validation
and execution are explicitly separate pending steps.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import ftplib
import hashlib
import json
from pathlib import Path
import re


def now():
    return datetime.now(timezone.utc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--launcher', type=Path, required=True)
    parser.add_argument('--credentials-file', type=Path, required=True)
    parser.add_argument('--remote-name', default='qingyu_bus_comparison_20261111.zip')
    parser.add_argument('--remote-launcher', default='qb')
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    launcher = args.launcher.resolve(strict=True)
    status_path = archive.parent / 'upload_status.json'
    status = json.loads(status_path.read_text(encoding='utf-8')) if status_path.exists() else {}
    if status.get('uploaded'):
        print(json.dumps({'action': 'already_transferred', 'remote_hash_verified': status.get('remote_hash_verified', False)}))
        return
    due = status.get('next_attempt_utc')
    if due and now() < datetime.fromisoformat(due):
        print(json.dumps({'action': 'backoff', 'next_attempt_utc': due}))
        return
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != args.sha256.lower():
        raise ValueError('Archive hash mismatch; no connection attempted')
    if launcher.name != 'qb' or not launcher.read_bytes().startswith(b'#!'):
        raise ValueError('Unexpected launcher; no connection attempted')
    text = args.credentials_file.read_text(encoding='utf-8-sig')
    users = set(re.findall(r'\bs4_\d+usr\b', text))
    passwords = set()
    # The user-maintained note precedes the forwarded initial account notice.
    # Prefer that explicit current credential, never alternate password guesses.
    current_notes = set(re.findall(r'^\s*密码是\s*(\S+)\s*$', text, re.MULTILINE))
    for line in text.splitlines():
        match = re.search(r'密码\s*[：:]\s*(\S+)', line)
        if 'linux' in line.lower() and match:
            value = match.group(1)
            if value.isascii() and 4 <= len(value) <= 100:
                passwords.add(value)
    credential_kind = 'explicit_current_note' if current_notes else 'initial_notice'
    if current_notes:
        passwords = current_notes
    if len(users) != 1 or len(passwords) != 1:
        raise ValueError('Existing credential record is ambiguous; no connection attempted')
    user, password = next(iter(users)), next(iter(passwords))
    del text, users, passwords, current_notes
    if (status.get('ftp_error', '').startswith('530') and
            status.get('credential_kind') == credential_kind):
        print(json.dumps({'action': 'authentication_failed_no_unchanged_retry',
                          'credential_kind': credential_kind}))
        return
    ftp = ftplib.FTP(timeout=20)
    started = now()
    remote_archive = args.remote_name
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.zip', remote_archive):
        raise ValueError('Remote archive name must be a plain ZIP filename')
    remote_launcher=args.remote_launcher
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', remote_launcher):
        raise ValueError('Remote launcher must be a plain filename')
    record = {'started_utc': started.isoformat(), 'phase': 'greeting',
              'uploaded': False, 'archive_sha256': digest, 'transfers': [],
              'credential_kind': credential_kind}
    try:
        ftp.connect('icdesigns0.nicu.cn', 18888, timeout=20)
        record['phase'] = 'authentication'
        ftp.login(user, password)
        ftp.set_pasv(True)
        for local, remote in [(archive, remote_archive), (launcher, remote_launcher)]:
            record['phase'] = 'transfer:' + remote
            with local.open('rb') as stream:
                ftp.storbinary('STOR ' + remote, stream, blocksize=65536)
            ftp.voidcmd('TYPE I')
            size = ftp.size(remote)
            if size != local.stat().st_size:
                raise ValueError('Remote size mismatch for ' + remote)
            record['transfers'].append({'file': remote, 'bytes': size, 'size_verified': True})
        record.update(uploaded=True, phase='transfer_complete')
    except (ftplib.Error, OSError, EOFError, ValueError) as exc:
        # Never log credential-bearing exception text or raw AUTH commands.
        message = str(exc).replace(password, '[redacted]').replace(user, '[account]')
        record['error'] = message[:400]
    finally:
        ftp.close()
    finished = now()
    failures = 0 if record['uploaded'] else int(status.get('consecutive_failures', 0)) + 1
    delay = [60, 300, 600][min(max(failures - 1, 0), 2)]
    status.update(checked_utc=finished.isoformat(), uploaded=record['uploaded'],
                  archive=remote_archive, archive_bytes=archive.stat().st_size,
                  archive_sha256=digest, launcher=remote_launcher, remote_execution_started=False,
                  remote_hash_verified=False, consecutive_failures=failures,
                  credential_kind=credential_kind,
                  ftp_error=record.get('error'), last_phase=record['phase'],
                  next_attempt_utc=None if record['uploaded'] else (finished + timedelta(seconds=delay)).isoformat())
    record['finished_utc'] = finished.isoformat()
    record['next_attempt_utc'] = status['next_attempt_utc']
    temporary = status_path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(status, indent=2) + '\n', encoding='utf-8')
    temporary.replace(status_path)
    with (archive.parent / 'upload_attempts.jsonl').open('a', encoding='utf-8') as log:
        log.write(json.dumps(record) + '\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
