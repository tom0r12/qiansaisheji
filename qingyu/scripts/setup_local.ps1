#requires -Version 5.1
<#
.SYNOPSIS
Detect or prepare the project's local Windows/WSL verification environment.
.DESCRIPTION
CheckOnly runs actual compiler/simulator checks and records local evidence. It
does not install packages or change vendor sources. A pinned Git checkout is
needed to verify E203; use E203Reference on the first CheckOnly invocation.
Normal setup installs missing Ubuntu packages and restores only missing/empty
E203 files from the pinned commit. Existing nonempty files are never replaced.
No command changes global PATH. Model setup is opt-in through WithModel.
#>
[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$WithModel,
    [string]$Distribution = 'Ubuntu',
    [string]$E203Reference
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$E203Commit = '9f3e34f337f5d0a1236a285871ffa2032491617a'
$E203Url = 'https://github.com/riscv-mcu/e203_hbirdv2.git'
$ReportDirectory = Join-Path $ProjectRoot 'reports'
$ConfigPath = Join-Path $ProjectRoot 'tool-config.local.json'
$Utf8 = New-Object System.Text.UTF8Encoding($false)
$Warnings = New-Object System.Collections.Generic.List[string]

function Save-Json([string]$Path, $Value) {
    [IO.File]::WriteAllText($Path, ($Value | ConvertTo-Json -Depth 30), $Utf8)
}

function Invoke-WslJson([string]$Code, [string[]]$Arguments = @()) {
    $stderrPath = [IO.Path]::GetTempFileName()
    try {
        $lines = & wsl.exe --distribution $Distribution --exec python3 -c $Code @Arguments 2> $stderrPath
        $status = $LASTEXITCODE
        $stderrText = [IO.File]::ReadAllText($stderrPath)
        if ($stderrText.Trim()) { $Warnings.Add($stderrText.Trim()) }
        $jsonLine = @($lines | Where-Object { ([string]$_).TrimStart().StartsWith('{') }) | Select-Object -Last 1
        if ($status -ne 0 -or -not $jsonLine) {
            throw "WSL Python check failed (exit $status). $stderrText $($lines -join [Environment]::NewLine)"
        }
        return ($jsonLine | ConvertFrom-Json)
    } finally {
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Convert-ToWslPath([string]$Path) {
    $lines = & wsl.exe --distribution $Distribution --exec wslpath -a -u $Path 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Cannot convert path for WSL: $Path" }
    $answer = @($lines | Where-Object { ([string]$_).StartsWith('/') }) | Select-Object -Last 1
    if (-not $answer) { throw "WSL did not return a Linux path for $Path" }
    return ([string]$answer).Trim()
}

function Invoke-Git([string[]]$Arguments) {
    & git @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Git command failed: git $($Arguments -join ' ')" }
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw 'WSL is not installed. Install and initialize Ubuntu before running this project setup.'
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw 'Git for Windows is required to obtain the fixed upstream source.'
}
[IO.Directory]::CreateDirectory($ReportDirectory) | Out-Null
$LinuxRoot = Convert-ToWslPath $ProjectRoot

$ProbeCode = @'
import importlib.util, json, os, pathlib, platform, shutil, subprocess, tempfile
tools = {}
versions = {'iverilog': ['-V'], 'vvp': ['-V']}
for name in ['python3', 'git', 'verilator', 'iverilog', 'vvp', 'g++', 'make',
             'riscv64-unknown-elf-gcc', 'riscv64-unknown-elf-objcopy']:
    path = shutil.which(name)
    item = {'path': path, 'found': bool(path)}
    if path:
        p = subprocess.run([path] + versions.get(name, ['--version']), capture_output=True, text=True)
        lines = (p.stdout + p.stderr).strip().splitlines()
        item.update(version=lines[0] if lines else '', version_exit_code=p.returncode)
    tools[name] = item
checks = {}
try:
    import numpy
    checks['numpy'] = {'passed': True, 'version': numpy.__version__}
except Exception as exc:
    checks['numpy'] = {'passed': False, 'error': str(exc)}
checks['venv'] = {'passed': bool(importlib.util.find_spec('venv')) and bool(importlib.util.find_spec('ensurepip'))}
with tempfile.TemporaryDirectory(prefix='qingyu-env-') as tmp:
    d = pathlib.Path(tmp)
    def run_check(name, commands):
        rows = []
        try:
            for command in commands:
                p = subprocess.run(command, cwd=d, capture_output=True, text=True, timeout=60)
                rows.append({'command': command, 'returncode': p.returncode,
                             'stdout': p.stdout[-2000:], 'stderr': p.stderr[-2000:]})
                if p.returncode:
                    raise RuntimeError('command failed')
            checks[name] = {'passed': True, 'commands': rows}
        except Exception as exc:
            checks[name] = {'passed': False, 'commands': rows, 'error': str(exc)}
    (d/'smoke.sv').write_text('`timescale 1ns/1ps\nmodule smoke; initial begin $display("LOCAL_SIM_OK"); $finish; end endmodule\n')
    (d/'smoke.cpp').write_text('#include <iostream>\nint main(){std::cout << "LOCAL_CXX_OK\\n";}\n')
    (d/'smoke.c').write_text('int square(int x) { return x*x; }\n')
    run_check('iverilog_simulation', [['iverilog', '-g2012', '-s', 'smoke', '-o', 'smoke.vvp', 'smoke.sv'], ['vvp', 'smoke.vvp']])
    run_check('verilator_lint', [['verilator', '--lint-only', '--top-module', 'smoke', 'smoke.sv']])
    run_check('host_cpp20', [['g++', '-std=c++20', 'smoke.cpp', '-o', 'smoke_cpp'], [str(d/'smoke_cpp')]])
    run_check('riscv_rv32imac_ilp32', [['riscv64-unknown-elf-gcc', '-march=rv32imac', '-mabi=ilp32', '-ffreestanding', '-c', 'smoke.c', '-o', 'smoke.o'],
                                    ['riscv64-unknown-elf-objcopy', '-O', 'binary', 'smoke.o', 'smoke.bin']])
    if checks['riscv_rv32imac_ilp32']['passed']:
        checks['riscv_rv32imac_ilp32']['elf_class'] = (d/'smoke.o').read_bytes()[4]
        checks['riscv_rv32imac_ilp32']['passed'] = checks['riscv_rv32imac_ilp32']['elf_class'] == 1
result = {'platform': platform.platform(), 'uid': os.getuid(), 'tools': tools, 'checks': checks,
          'ready': all(v['found'] for v in tools.values()) and all(v['passed'] for v in checks.values())}
print(json.dumps(result))
'@

$Probe = $null
try { $Probe = Invoke-WslJson $ProbeCode } catch {
    if ($CheckOnly) { throw }
    Write-Host "Initial environment check could not run: $($_.Exception.Message)"
}
if (-not $CheckOnly -and (-not $Probe -or -not $Probe.ready)) {
    Write-Host 'Installing missing local verification dependencies in WSL Ubuntu.'
    & wsl.exe --distribution $Distribution --user root --exec apt-get update
    if ($LASTEXITCODE -ne 0) { throw 'apt-get update failed; existing sources and global PATH were not changed.' }
    & wsl.exe --distribution $Distribution --user root --exec apt-get install -y verilator iverilog g++ make git python3 python3-venv python3-numpy gcc-riscv64-unknown-elf binutils-riscv64-unknown-elf
    if ($LASTEXITCODE -ne 0) { throw 'apt-get install failed.' }
    $Probe = Invoke-WslJson $ProbeCode
}

if (-not $E203Reference -and (Test-Path -LiteralPath $ConfigPath)) {
    $Previous = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
    if ($Previous.vendor.e203.reference_windows -and
        (Test-Path -LiteralPath $Previous.vendor.e203.reference_windows)) {
        $E203Reference = $Previous.vendor.e203.reference_windows
    }
}
if (-not $E203Reference) {
    $E203Reference = Join-Path $ProjectRoot "build/vendor_refs/e203_hbirdv2-$E203Commit"
}
$E203Reference = [IO.Path]::GetFullPath($E203Reference)
$E203ReferenceReady = Test-Path -LiteralPath (Join-Path $E203Reference '.git')
if (-not $E203ReferenceReady -and -not $CheckOnly) {
    if ((Test-Path -LiteralPath $E203Reference) -and
        @(Get-ChildItem -LiteralPath $E203Reference -Force).Count -gt 0) {
        throw "Reference directory contains non-Git files; refusing to replace them: $E203Reference"
    }
    [IO.Directory]::CreateDirectory($E203Reference) | Out-Null
    Invoke-Git @('init', $E203Reference)
    Invoke-Git @('-C', $E203Reference, 'remote', 'add', 'origin', $E203Url)
    Invoke-Git @('-C', $E203Reference, 'fetch', '--depth', '1', 'origin', $E203Commit)
    # No checkout is needed: verification/restoration uses canonical Git blobs.
    $E203ReferenceReady = $true
}

$E203 = [pscustomobject]@{ ready=$false; commit=$E203Commit; error='Pinned reference unavailable. Run normal setup or pass -E203Reference with the fixed upstream Git checkout.' }
if ($E203ReferenceReady) {
    $ReferenceLinux = Convert-ToWslPath $E203Reference
    $E203Code = @'
import hashlib, json, pathlib, subprocess, sys
reference, project, commit, restore = sys.argv[1:]
root = pathlib.Path(project).resolve()
vendor = root/'vendor/e203_hbirdv2'
def git(*args):
    return subprocess.check_output(['git', '-c', 'safe.directory='+reference, '-C', reference, *args])
try:
    resolved = git('rev-parse', commit+'^{commit}').decode().strip()
    if resolved != commit:
        raise ValueError('Pinned commit did not resolve exactly')
    rows = git('ls-tree', '-r', '-z', commit, '--', 'rtl', 'LICENSE').split(b'\0')
    expected = {}
    for row in rows:
        if row:
            info, filename = row.split(b'\t', 1)
            mode, kind, oid = info.split()
            if kind != b'blob' or mode not in (b'100644', b'100755'):
                raise ValueError('Unexpected upstream file type')
            expected[filename.decode()] = oid.decode()
    if len(expected) < 50 or 'LICENSE' not in expected:
        raise ValueError('Incomplete upstream source tree')
    if not vendor.resolve().is_relative_to(root):
        raise ValueError('Vendor path escapes the project')
    files, missing, modified, restored, eol = {}, [], [], [], []
    for name, oid in sorted(expected.items()):
        path = vendor/name
        if not path.resolve().is_relative_to(vendor.resolve()):
            raise ValueError('Vendor file path escapes its directory: '+name)
        if not path.is_file() or path.stat().st_size == 0:
            if restore == '1':
                if path.exists() and not path.is_file():
                    raise ValueError('Non-file target cannot be restored: '+name)
                data = git('cat-file', 'blob', oid)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                restored.append(name)
            else:
                missing.append(name)
                continue
        data = path.read_bytes()
        def blob_hash(content):
            return hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()
        raw_match = blob_hash(data) == oid
        eol_match = not raw_match and blob_hash(data.replace(b'\r\n', b'\n')) == oid
        if not (raw_match or eol_match):
            modified.append(name)
        if eol_match:
            eol.append(name)
        files[name] = {'git_blob': oid, 'sha256': hashlib.sha256(data).hexdigest(),
                       'matches_commit': raw_match or eol_match, 'crlf_only_difference': eol_match}
    extras = []
    if (vendor/'rtl').is_dir():
        extras = sorted(str(p.relative_to(vendor)) for p in (vendor/'rtl').rglob('*')
                        if p.is_file() and p.relative_to(vendor).as_posix() not in expected)
    result = {'ready': not missing and not modified, 'commit': commit,
              'reference': reference, 'expected_files': len(expected), 'verified_files': len(files)-len(modified),
              'missing': missing, 'modified_preserved': modified, 'restored': restored,
              'crlf_equivalent_files': eol, 'extra_files_preserved': extras, 'files': files}
except Exception as exc:
    result = {'ready': False, 'commit': commit, 'error': str(exc)}
print(json.dumps(result))
'@
    $RestoreFlag = if ($CheckOnly) { '0' } else { '1' }
    $E203 = Invoke-WslJson $E203Code @($ReferenceLinux, $LinuxRoot, $E203Commit, $RestoreFlag)
}
Save-Json (Join-Path $ReportDirectory 'e203-source-manifest.json') $E203

$Native = [ordered]@{}
foreach ($entry in @(
    @{name='iverilog'; candidates=@((Join-Path 'G:\iverilog\bin' 'iverilog.exe'))},
    @{name='vvp'; candidates=@((Join-Path 'G:\iverilog\bin' 'vvp.exe'))},
    @{name='riscv-none-elf-gcc'; candidates=@('D:\efinity-riscv-ide\toolchain\bin\riscv-none-elf-gcc.exe')},
    @{name='model_python'; candidates=@((Join-Path $ProjectRoot '.venv-model/Scripts/python.exe'))}
)) {
    $found = Get-Command $entry.name -ErrorAction SilentlyContinue | Select-Object -First 1
    $path = if ($found) { $found.Source } else { $entry.candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1 }
    $version = $null
    if ($path) {
        $flag = if ($entry.name -in @('iverilog','vvp')) { '-V' } else { '--version' }
        $version = (& $path $flag 2>$null | Select-Object -First 1)
    }
    $Native[$entry.name] = [ordered]@{path=$path; found=[bool]$path; version=$version}
}

$ModelSetup = 'not requested; local HDL verification does not require TensorFlow'
if ($WithModel) {
    $ModelScript = Join-Path $PSScriptRoot 'setup_model.ps1'
    if (-not (Test-Path -LiteralPath $ModelScript)) { throw 'scripts/setup_model.ps1 is not available.' }
    if ($CheckOnly) {
        $ModelSetup = 'CheckOnly: model installer skipped; inspect reports/model_environment.json and run its smoke check separately'
    } else {
        & $ModelScript
        if ($LASTEXITCODE -ne 0) { throw 'Model environment setup failed.' }
        $ModelSetup = 'setup_model.ps1 completed'
    }
}

$Ready = [bool]$Probe.ready -and [bool]$E203.ready
$Config = [ordered]@{
    schema_version=1; generated_utc=[DateTime]::UtcNow.ToString('o'); project_root=$ProjectRoot
    default_execution='wsl'; path_scope='project commands only; global PATH unchanged'
    wsl=[ordered]@{distribution=$Distribution; project_root=$LinuxRoot; tools=$Probe.tools}
    native=$Native
    vendor=[ordered]@{e203=[ordered]@{commit=$E203Commit; upstream=$E203Url; reference_windows=$E203Reference; manifest='reports/e203-source-manifest.json'; verified=[bool]$E203.ready}}
    external_eda=[ordered]@{verified=$false; note='Commercial EDA, licensed PDK/SRAM and the competition server are not verified by this local setup.'}
}
$Environment = [ordered]@{
    generated_utc=$Config.generated_utc; check_only=[bool]$CheckOnly; ready=$Ready
    distribution=$Distribution; project_root=$ProjectRoot; wsl=$Probe; native=$Native
    e203=[ordered]@{ready=[bool]$E203.ready; commit=$E203Commit; expected_files=$E203.expected_files; verified_files=$E203.verified_files; missing=$E203.missing; modified_preserved=$E203.modified_preserved; error=$E203.error; manifest='reports/e203-source-manifest.json'}
    model_setup=$ModelSetup; external_eda=$Config.external_eda; warnings=@($Warnings)
}
Save-Json $ConfigPath $Config
Save-Json (Join-Path $ReportDirectory 'environment.json') $Environment
Write-Host "WSL tools and compiler checks: $($Probe.ready)"
Write-Host "Pinned E203 source verification: $($E203.ready) ($($E203.verified_files)/$($E203.expected_files) files)"
Write-Host "Environment report: $(Join-Path $ReportDirectory 'environment.json')"
if (-not $Ready) {
    Write-Error 'Local setup is incomplete. See reports/environment.json; existing nonempty vendor files were preserved.'
    exit 1
}
Write-Host 'Local verification environment is ready. Use scripts/local.ps1 for project commands.'
