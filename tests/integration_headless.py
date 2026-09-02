#!/usr/bin/env python3
"""
integration_headless.py — Live integration tests against NatronRenderer -t.

Run with:
    python tests/integration_headless.py

Single-phase startup:
    NatronRenderer -t -s startup.py

The startup script creates test nodes before app.exec_() so they exist when
the TCP tests run. createNode/createWriter work fine before exec_(); they
return None from QTimer callbacks while exec_() is running (re-entrancy
restriction in NatronRenderer).

Note: load_project causes a SIGSEGV in NatronRenderer headless mode due to
Natron's Python attribute binder failing to resolve app.NodeName. Documented
in BEST_PRACTICES.md. load_project is not tested here.
"""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from natron_detect import find_natron_install

PORT          = 54321
POLL_INTERVAL = 1.0
POLL_TIMEOUT  = 30

NAMES_FILE    = Path('/tmp/natron_integration_names.txt')
SAVE_PATH     = '/tmp/natron_mcp_integration_result.ntp'

# ---------------------------------------------------------------------------
# Startup script — runs inside NatronRenderer before exec_()
# ---------------------------------------------------------------------------

STARTUP_SCRIPT = r"""
import __main__
from PySide.QtCore import QCoreApplication

app = getattr(__main__, 'app1', None)

grade = app.createNode('net.sf.openfx.GradePlugin')
grade.setLabel('MyGrade')
grade.getParam('multiply').setValue(1.0)

grade2 = app.createNode('net.sf.openfx.GradePlugin')
grade2.setLabel('Grade2')

bd = app.createNode('fr.inria.built-in.BackDrop')
bd.setLabel('Test Backdrop')

writer = app.createWriter('/tmp/natron_mcp_test_out.####.exr')
writer.connectInput(0, grade)

names = [n.getScriptName() for n in app.getChildren()]
with open('/tmp/natron_integration_names.txt', 'w') as f:
    f.write('\n'.join(names))

qt_app = QCoreApplication.instance()
if qt_app is not None:
    qt_app.exec_()
else:
    import sys as _sys
    print('[natron-mcp] ERROR: no QCoreApplication — keepalive failed', file=_sys.stderr)
"""


# ---------------------------------------------------------------------------
# TCP helpers
# ---------------------------------------------------------------------------

def _recv_line(sock: socket.socket) -> bytes:
    buf = b''
    while b'\n' not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise OSError('Connection closed')
        buf += chunk
    return buf.split(b'\n')[0]


def _call(sock: socket.socket, method: str, req_id: int, **params) -> dict:
    req = json.dumps({'id': req_id, 'method': method, 'params': params})
    sock.sendall((req + '\n').encode())
    return json.loads(_recv_line(sock))


def _ping_ok() -> bool:
    try:
        s = socket.create_connection(('127.0.0.1', PORT), timeout=1)
        s.settimeout(2)
        r = _call(s, 'ping', 0)
        s.close()
        return r.get('result', {}).get('status') == 'ok'
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Test runner helpers
# ---------------------------------------------------------------------------

_results: list[tuple[str, bool, str]] = []
_req_id = 0


def check(name: str, ok: bool, detail: str = ''):
    _results.append((name, ok, detail))
    status = 'PASS' if ok else 'FAIL'
    suffix = f'  ({detail})' if detail else ''
    print(f'  [{status}] {name}{suffix}')


def call(sock: socket.socket, method: str, **params) -> dict:
    global _req_id
    _req_id += 1
    return _call(sock, method, _req_id, **params)


def wait_for_server(proc: subprocess.Popen) -> None:
    print(f'  PID {proc.pid} — waiting for :{PORT}', end='', flush=True)
    elapsed = 0.0
    while not _ping_ok():
        if proc.poll() is not None:
            out, _ = proc.communicate()
            print(f'\nERROR: NatronRenderer exited (rc={proc.returncode})')
            print(out.decode(errors='replace'))
            sys.exit(1)
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        print('.', end='', flush=True)
        if elapsed >= POLL_TIMEOUT:
            proc.kill()
            print('\nERROR: timeout')
            sys.exit(1)
    print(' ready.')


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    install = find_natron_install()
    if install is None:
        print('ERROR: Natron not found')
        sys.exit(1)

    renderer = install / 'NatronRenderer'
    if not renderer.exists():
        print(f'ERROR: NatronRenderer not found at {renderer}')
        sys.exit(1)

    startup_path = Path('/tmp/natron_integration_startup.py')
    startup_path.write_text(STARTUP_SCRIPT)
    NAMES_FILE.unlink(missing_ok=True)

    print('Starting NatronRenderer with test nodes...')
    proc = subprocess.Popen(
        [str(renderer), '-t', '-s', str(startup_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_for_server(proc)

    # Read node names written by the startup script
    deadline = time.monotonic() + 10
    while not NAMES_FILE.exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    if not NAMES_FILE.exists():
        proc.kill()
        print('ERROR: startup script did not write node names')
        sys.exit(1)

    node_names = NAMES_FILE.read_text().strip().splitlines()
    print(f'  Nodes: {node_names}\n')

    grade  = next(n for n in node_names if n.startswith('Grade') and '2' not in n)
    grade2 = next(n for n in node_names if n.startswith('Grade') and '2' in n)
    writer = next(n for n in node_names if 'Write' in n or 'write' in n.lower())

    try:
        s = socket.create_connection(('127.0.0.1', PORT), timeout=5)
        s.settimeout(15)
        _run_tests(s, grade, grade2, writer)
        s.close()
    finally:
        proc.kill()
        proc.wait()
        print('\nNatronRenderer stopped.')

    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    print(f'\n{passed} passed, {failed} failed')
    if failed:
        print('\nFailed tests:')
        for name, ok, detail in _results:
            if not ok:
                print(f'  FAIL: {name}' + (f' ({detail})' if detail else ''))
        sys.exit(1)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def _run_tests(s: socket.socket, grade: str, grade2: str, writer: str):
    print('=== ping ===')
    r = call(s, 'ping')
    check('returns ok', r.get('result', {}).get('status') == 'ok')
    check('has natron_version', 'natron_version' in r.get('result', {}))

    print('\n=== get_scene_info ===')
    r = call(s, 'get_scene_info')
    res = r.get('result', {})
    check('no error', 'error' not in r, r.get('error', ''))
    check('has node_count', 'node_count' in res)
    check('nodes loaded', res.get('node_count', 0) > 0, str(res.get('node_count')))

    print('\n=== list_nodes ===')
    r = call(s, 'list_nodes')
    check('no error', 'error' not in r, r.get('error', ''))
    nodes = r.get('result', {}).get('nodes', [])
    names = [n['script_name'] for n in nodes]
    check('grade node present', grade in names, str(names))

    print('\n=== list_plugin_ids (all) ===')
    r = call(s, 'list_plugin_ids', filter='')
    check('no error', 'error' not in r, r.get('error', ''))
    all_ids = r.get('result', {}).get('plugin_ids', [])
    check('returns IDs', len(all_ids) > 0, f'{len(all_ids)} IDs')
    check('contains Grade', any('Grade' in i or 'grade' in i for i in all_ids))

    print('\n=== list_plugin_ids (filtered) ===')
    r = call(s, 'list_plugin_ids', filter='merge')
    check('no error', 'error' not in r, r.get('error', ''))
    filtered = r.get('result', {}).get('plugin_ids', [])
    check('filter narrows results', 0 < len(filtered) < len(all_ids),
          f'{len(filtered)} vs {len(all_ids)}')

    print('\n=== get_node_info ===')
    r = call(s, 'get_node_info', script_name=grade)
    check('no error', 'error' not in r, r.get('error', ''))
    info = r.get('result', {})
    check('has inputs', 'inputs' in info)
    check('has params', 'params' in info)

    print('\n=== get_parameter ===')
    r = call(s, 'get_parameter', node=grade, param='multiply')
    check('no error', 'error' not in r, r.get('error', ''))
    check('multiply is 1.0', r.get('result', {}).get('value') == 1.0,
          str(r.get('result', {}).get('value')))

    print('\n=== set_parameter ===')
    r = call(s, 'set_parameter', node=grade, param='multiply', value=1.8)
    check('no error', 'error' not in r, r.get('error', ''))
    r = call(s, 'get_parameter', node=grade, param='multiply')
    check('reads back 1.8', r.get('result', {}).get('value') == 1.8,
          str(r.get('result', {}).get('value')))

    print('\n=== set_node_label ===')
    r = call(s, 'set_node_label', script_name=grade, label='TestGrade')
    check('no error', 'error' not in r, r.get('error', ''))
    check('label updated', r.get('result', {}).get('label') == 'TestGrade')

    print('\n=== set_node_color ===')
    r = call(s, 'set_node_color', script_name=grade, r=0.2, g=0.6, b=0.9)
    check('no error', 'error' not in r, r.get('error', ''))
    color = r.get('result', {})
    check('r/g/b in result', all(k in color for k in ('r', 'g', 'b')))

    print('\n=== set_node_position ===')
    r = call(s, 'set_node_position', script_name=grade, x=100.0, y=200.0)
    check('no error', 'error' not in r, r.get('error', ''))
    pos = r.get('result', {})
    check('x/y in result', 'x' in pos and 'y' in pos)

    print('\n=== modify_node ===')
    r = call(s, 'modify_node', node=grade, params={'multiply': 1.5, 'gamma': 0.9})
    check('no error', 'error' not in r, r.get('error', ''))
    updated = r.get('result', {}).get('updated', [])
    check('multiply in updated', 'multiply' in updated)
    check('gamma in updated', 'gamma' in updated)
    r = call(s, 'get_parameter', node=grade, param='multiply')
    check('multiply reads back 1.5', r.get('result', {}).get('value') == 1.5,
          str(r.get('result', {}).get('value')))

    print('\n=== find_nodes_by_type ===')
    r = call(s, 'find_nodes_by_type', plugin_id='net.sf.openfx.GradePlugin')
    check('no error', 'error' not in r, r.get('error', ''))
    found = [n['script_name'] for n in r.get('result', {}).get('nodes', [])]
    check('finds grade', grade in found, str(found))
    check('finds grade2', grade2 in found, str(found))

    print('\n=== batch_set_knob ===')
    r = call(s, 'batch_set_knob', nodes=[grade, grade2], param='multiply', value=2.0)
    check('no error', 'error' not in r, r.get('error', ''))
    updated = set(r.get('result', {}).get('updated', []))
    check('both nodes updated', updated == {grade, grade2}, str(updated))
    r = call(s, 'get_parameter', node=grade2, param='multiply')
    check('grade2 multiply is 2.0', r.get('result', {}).get('value') == 2.0,
          str(r.get('result', {}).get('value')))

    print('\n=== connect_nodes ===')
    r = call(s, 'connect_nodes', src=grade, dst=grade2, input_index=0)
    check('no error', 'error' not in r, r.get('error', ''))
    check('ok is True', r.get('result', {}).get('ok') is True)

    print('\n=== get_frame ===')
    r = call(s, 'get_frame')
    check('no error', 'error' not in r, r.get('error', ''))
    check('frame is int', isinstance(r.get('result', {}).get('frame'), int))

    print('\n=== set_project_settings ===')
    r = call(s, 'set_project_settings', fps=25.0, first_frame=1, last_frame=50)
    check('no error', 'error' not in r, r.get('error', ''))

    print('\n=== set_frame (expected error: no GuiApp headlessly) ===')
    r = call(s, 'set_frame', frame=10)
    check('errors cleanly', 'error' in r, r.get('error', 'no error'))

    print('\n=== save_project ===')
    r = call(s, 'save_project', filename=SAVE_PATH)
    check('no error', 'error' not in r, r.get('error', ''))
    check('file on disk', os.path.exists(SAVE_PATH), SAVE_PATH)

    print('\n=== delete_node ===')
    r = call(s, 'delete_node', script_name=grade)
    check('no error', 'error' not in r, r.get('error', ''))
    r = call(s, 'list_nodes')
    names = [n['script_name'] for n in r.get('result', {}).get('nodes', [])]
    check('grade removed', grade not in names, str(names))

    print('\n=== execute_python ===')
    r = call(s, 'execute_python', code='_result = 2 + 2')
    check('no error', 'error' not in r, r.get('error', ''))
    check('result is 4', r.get('result', {}).get('result') == 4)


if __name__ == '__main__':
    main()
