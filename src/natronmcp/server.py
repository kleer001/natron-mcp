"""
server.py — TCP JSON server that runs inside Natron's embedded Python.

Loaded via ~/.Natron/init.py at startup. Listens on TCP port 54321 for
newline-delimited JSON commands, executes them via NatronEngine, and returns
newline-delimited JSON responses.

Protocol:
  Request:  {"id": <int>, "method": "<name>", "params": {...}}\n
  Response: {"id": <int>, "result": {...}}\n
         or {"id": <int>, "error": "<message>"}\n

Thread safety: NatronEngine (Qt4) is not safe to call from background threads.
start() is called from Natron's main thread (via init.py) and installs a
PySide QTimer that polls a work queue every 10ms. Socket handler threads put
tasks on the queue and block on a threading.Event; the timer drains the queue
on the main thread and sets the event when done.
"""

import json
import queue as _queue
import socketserver
import threading
import traceback

PORT = 54321

# Work queue drained by the main-thread QTimer.
_work_queue: '_queue.Queue' = _queue.Queue()
_drain_timer = None  # holds QTimer reference so GC doesn't collect it


# ---------------------------------------------------------------------------
# App / node / param accessors — raise on failure so _handle_line catches them
# ---------------------------------------------------------------------------

def _get_app():
    """Return the first Natron App instance, or None if no project is open."""
    try:
        import __main__
        for name in ('app1', 'app2', 'app'):
            a = getattr(__main__, name, None)
            if a is not None:
                return a
        return None
    except Exception:
        return None


def _require_app():
    app = _get_app()
    if app is None:
        raise RuntimeError('No project open')
    return app


def _require_node(app, name: str):
    node = app.getNode(name)
    if node is None:
        raise RuntimeError(f'Node not found: {name}')
    return node


def _require_param(node, name: str):
    param = node.getParam(name)
    if param is None:
        raise RuntimeError(f'Param not found: {name}')
    return param


# ---------------------------------------------------------------------------
# Main-thread dispatch
# ---------------------------------------------------------------------------

def _drain_work_queue():
    """Called by the QTimer on Natron's main thread every 10ms."""
    while True:
        try:
            task = _work_queue.get_nowait()
        except _queue.Empty:
            break
        task()


def _run_on_main_thread(fn, timeout=10.0):
    """
    Execute fn() on the Qt main thread via the work queue.
    Raises RuntimeError on timeout, propagates exceptions from fn.
    """
    evt = threading.Event()
    box = [None, None]  # [result, exc]

    def _task():
        try:
            box[0] = fn()
        except Exception as e:
            box[1] = e
        finally:
            evt.set()

    _work_queue.put(_task)
    if not evt.wait(timeout=timeout):
        raise RuntimeError(f'Main-thread call timed out after {timeout}s')
    if box[1] is not None:
        raise box[1]
    return box[0]


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------

def _dispatch(method: str, params: dict) -> dict:
    # ping runs inline — it barely touches NatronEngine
    if method == 'ping':
        return _cmd_ping(params)
    if method == 'restart_server':
        return _cmd_restart_server(params)

    # All other commands marshal to main thread
    handlers = {
        'get_scene_info':  _cmd_get_scene_info,
        'list_nodes':      _cmd_list_nodes,
        'create_node':     _cmd_create_node,
        'get_node_info':   _cmd_get_node_info,
        'set_parameter':   _cmd_set_parameter,
        'get_parameter':   _cmd_get_parameter,
        'connect_nodes':   _cmd_connect_nodes,
        'delete_node':     _cmd_delete_node,
        'execute_python':  _cmd_execute_python,
    }
    handler = handlers.get(method)
    if handler is None:
        raise ValueError(f'Unknown method: {method}')
    return _run_on_main_thread(lambda: handler(params))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def _cmd_ping(_params):
    try:
        import NatronEngine
        ver = NatronEngine.natron.getNatronVersionString()
    except Exception:
        ver = 'unknown'
    return {'status': 'ok', 'natron_version': ver}


def _cmd_restart_server(params):
    port = int(params.get('port', PORT))
    threading.Thread(target=_restart, args=(port,), daemon=True).start()
    return {'ok': True, 'restarting_on_port': port}


def _cmd_get_scene_info(_params):
    app = _require_app()
    try:
        proj  = app.getProjectParam
        name  = proj('projectName').getValue()
        fps   = proj('frameRate').getValue()
        first = int(proj('firstFrame').getValue())
        last  = int(proj('lastFrame').getValue())
    except Exception:
        name, fps, first, last = '', 24.0, 1, 100
    nodes = app.getChildren()
    return {
        'project_name': name,
        'frame_rate':   fps,
        'frame_range':  [first, last],
        'node_count':   len(nodes),
    }


def _cmd_list_nodes(_params):
    app = _require_app()
    return {'nodes': [
        {'script_name': n.getScriptName(), 'label': n.getLabel(), 'plugin_id': n.getPluginID()}
        for n in app.getChildren()
    ]}


def _cmd_create_node(params):
    plugin_id = params.get('plugin_id')
    if not plugin_id:
        raise ValueError('plugin_id required')
    app  = _require_app()
    node = app.createNode(plugin_id)
    if node is None:
        raise RuntimeError(f'Failed to create node: {plugin_id}')
    return {'script_name': node.getScriptName(), 'label': node.getLabel(), 'plugin_id': node.getPluginID()}


def _cmd_get_node_info(params):
    name = params.get('script_name')
    if not name:
        raise ValueError('script_name required')
    node = _require_node(_require_app(), name)

    inputs = [
        (node.getInput(i).getScriptName() if node.getInput(i) else None)
        for i in range(node.getMaxInputCount())
    ]
    param_names = []
    try:
        param_names = [p.getScriptName() for p in node.getParams()]
    except Exception:
        pass

    return {
        'script_name': node.getScriptName(),
        'label':       node.getLabel(),
        'plugin_id':   node.getPluginID(),
        'inputs':      inputs,
        'params':      param_names,
    }


def _cmd_get_parameter(params):
    node_name  = params.get('node')
    param_name = params.get('param')
    if not node_name or not param_name:
        raise ValueError('node and param required')
    param = _require_param(_require_node(_require_app(), node_name), param_name)
    try:
        value = param.getValue()
    except Exception:
        value = None
    return {'node': node_name, 'param': param_name, 'value': value}


def _cmd_set_parameter(params):
    node_name  = params.get('node')
    param_name = params.get('param')
    value      = params.get('value')
    if node_name is None or param_name is None or value is None:
        raise ValueError('node, param, and value required')
    param = _require_param(_require_node(_require_app(), node_name), param_name)
    param.setValue(value)
    return {'ok': True, 'node': node_name, 'param': param_name, 'value': value}


def _cmd_connect_nodes(params):
    src_name  = params.get('src')
    dst_name  = params.get('dst')
    input_idx = int(params.get('input_index', 0))
    if not src_name or not dst_name:
        raise ValueError('src and dst required')
    app = _require_app()
    src = _require_node(app, src_name)
    dst = _require_node(app, dst_name)
    ok  = dst.connectInput(input_idx, src)
    return {'ok': bool(ok), 'src': src_name, 'dst': dst_name, 'input_index': input_idx}


def _cmd_delete_node(params):
    name = params.get('script_name')
    if not name:
        raise ValueError('script_name required')
    node = _require_node(_require_app(), name)
    node.destroy()
    return {'ok': True, 'deleted': name}


def _cmd_execute_python(params):
    code = params.get('code', '')
    if not code:
        raise ValueError('code required')
    import __main__
    import io
    import sys
    ns  = vars(__main__).copy()
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        exec(compile(code, '<natron_mcp>', 'exec'), ns)
        output = buf.getvalue()
    finally:
        sys.stdout = old_stdout
    result = ns.get('_result', None)
    return {'output': output, 'result': result}


# ---------------------------------------------------------------------------
# TCP server
# ---------------------------------------------------------------------------

class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        conn = self.request
        conn.settimeout(None)
        buf = b''
        while True:
            try:
                chunk = conn.recv(4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                line = line.strip()
                if not line:
                    continue
                self._handle_line(conn, line)

    def _handle_line(self, conn, line: bytes):
        req_id = None
        try:
            data   = json.loads(line)
            req_id = data.get('id')
            result = _dispatch(data['method'], data.get('params', {}))
            response = json.dumps({'id': req_id, 'result': result})
        except Exception as exc:
            tb = traceback.format_exc()
            response = json.dumps({'id': req_id, 'error': str(exc), 'traceback': tb})
        try:
            conn.sendall((response + '\n').encode())
        except OSError:
            pass


class _Server(socketserver.TCPServer):
    allow_reuse_address = True


_server_instance = None
_server_thread   = None


def _restart(port: int = PORT):
    global _server_instance, _server_thread
    if _server_instance is not None:
        try:
            _server_instance.shutdown()
        except Exception:
            pass
        _server_instance = None
    # Reuse the existing QTimer — don't create a new one from this bg thread.
    # Just restart the TCP listener.
    _server_instance = _Server(('127.0.0.1', port), _Handler)
    _server_thread = threading.Thread(
        target=_server_instance.serve_forever,
        name='natron-mcp-server',
        daemon=True,
    )
    _server_thread.start()
    print(f'[natron-mcp] TCP server restarted on 127.0.0.1:{port}')


def start(port: int = PORT):
    global _server_instance, _server_thread, _drain_timer
    if _server_instance is not None:
        return  # already running

    # Install a QTimer on the calling thread (Natron's main thread via init.py).
    # It drains _work_queue every 10ms so NatronEngine calls always run on main.
    try:
        from PySide.QtCore import QTimer
        _drain_timer = QTimer()
        _drain_timer.timeout.connect(_drain_work_queue)
        _drain_timer.start(10)
        print('[natron-mcp] Main-thread QTimer installed (10ms poll)')
    except Exception as e:
        print(f'[natron-mcp] WARNING: QTimer setup failed ({e}); NatronEngine calls will run on socket thread')

    _server_instance = _Server(('127.0.0.1', port), _Handler)
    _server_thread = threading.Thread(
        target=_server_instance.serve_forever,
        name='natron-mcp-server',
        daemon=True,
    )
    _server_thread.start()
    print(f'[natron-mcp] TCP server listening on 127.0.0.1:{port}')


def stop():
    global _server_instance
    if _server_instance:
        _server_instance.shutdown()
        _server_instance = None
