"""Encode the local read-only status helper for the existing VNC terminal."""
from pathlib import Path
import argparse,base64,zlib
H=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--precision-search',action='store_true');a=ap.parse_args()
name='find_precision_inputs.py'if a.precision_search else'status_native.py'
destination='find_precision_launch.txt'if a.precision_search else'status_launch.txt'
payload=base64.b64encode(zlib.compress((H/name).read_bytes(),9)).decode()
(H/destination).write_text("python3 -c 'import base64,zlib;exec(zlib.decompress(base64.b64decode(\""+payload+"\")))'")
