#!/usr/bin/env python3
"""
launch.py — Launch Natron and wait for the MCP TCP server to be ready.

Usage:
    python scripts/launch.py                    # open most recent project, or new untitled
    python scripts/launch.py /path/to/file.ntp  # open specific project
    python scripts/launch.py --headless         # launch NatronRenderer -t (no GUI)

Polls the MCP TCP port (54321) until Natron responds to a ping, then exits.
"""

import argparse
import configparser
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path


NATRON_BASE = Path('/media/menser/fauna/META_VFX/software/natron/Natron-2.5.0-Linux-x86_64-no-installer')
NATRON_BIN  = NATRON_BASE / 'Natron'
RENDERER_BIN = NATRON_BASE / 'NatronRenderer'
NATRON_CONF = Path.home() / '.config' / 'INRIA' / 'Natron.conf'
MCP_PORT    = 54321
POLL_INTERVAL = 1.0
POLL_TIMEOUT  = 30


def _most_recent_project() -> str | None:
    """Read the most recent project path from Natron.conf."""
    if not NATRON_CONF.exists():
        return None
    # Natron.conf is an INI-style file; recentFileList is a comma-separated value
    # under [General] or at the top level.
    text = NATRON_CONF.read_text()
    for line in text.splitlines():
        if line.startswith('recentFileList='):
            value = line.split('=', 1)[1].strip()
            if value:
                first = value.split(',')[0].strip()
                if first and Path(first).exists():
                    return first
    return None


def _ping(port: int) -> bool:
    try:
        s = socket.create_connection(('127.0.0.1', port), timeout=1)
        req = json.dumps({'id': 1, 'method': 'ping', 'params': {}})
        s.sendall((req + '\n').encode())
        s.settimeout(2)
        data = s.recv(4096)
        s.close()
        resp = json.loads(data.split(b'\n')[0])
        return resp.get('result', {}).get('status') == 'ok'
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description='Launch Natron with MCP server')
    parser.add_argument('project', nargs='?', help='Path to .ntp project file')
    parser.add_argument('--headless', action='store_true',
                        help='Launch NatronRenderer in terminal mode (no GUI)')
    args = parser.parse_args()

    if args.headless:
        binary = RENDERER_BIN
        if not binary.exists():
            print(f'Error: NatronRenderer not found at {binary}', file=sys.stderr)
            sys.exit(1)
        cmd = [str(binary), '-t']
        if args.project:
            cmd.append(args.project)
    else:
        binary = NATRON_BIN
        if not binary.exists():
            print(f'Error: Natron not found at {binary}', file=sys.stderr)
            sys.exit(1)
        project = args.project or _most_recent_project()
        if project:
            print(f'Opening project: {project}')
            cmd = [str(binary), project]
        else:
            print('No recent project found — Natron will start with an untitled project')
            cmd = [str(binary)]

    proc = subprocess.Popen(cmd)
    print(f'Natron PID: {proc.pid}')

    print(f'Waiting for MCP server on port {MCP_PORT}', end='', flush=True)
    elapsed = 0.0
    while True:
        if _ping(MCP_PORT):
            print()
            print('MCP server ready.')
            break

        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        print('.', end='', flush=True)

        if elapsed >= POLL_TIMEOUT:
            print()
            print(f'ERROR: MCP server did not respond after {POLL_TIMEOUT}s.', file=sys.stderr)
            print('Check that ~/.Natron/init.py is loading natronmcp correctly.', file=sys.stderr)
            sys.exit(1)

    print('Natron is ready.')


if __name__ == '__main__':
    main()
