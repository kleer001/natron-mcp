"""
natron_mcp_server.py — MCP server (stdio) that bridges Claude ↔ Natron TCP server.

Run with:
  python natron_mcp_server.py
  # or via uv:
  uv run natron_mcp_server.py

Connects to natronmcp running inside Natron on 127.0.0.1:54321.
Start Natron first (scripts/launch.py) so the TCP server is ready.
"""

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).parent))
import natron_rag

NATRON_HOST = '127.0.0.1'
NATRON_PORT = 54321

mcp = FastMCP('natron')

# ---------------------------------------------------------------------------
# TCP client (persistent connection with auto-reconnect on broken pipe)
# ---------------------------------------------------------------------------

class _NatronClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._id = 0

    def _connect(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10)
        s.connect((self.host, self.port))
        self._sock = s

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _send_recv(self, req: str) -> str:
        self._sock.sendall((req + '\n').encode())
        return self._recv_line()

    def call(self, method: str, params: dict | None = None, timeout: float = 10.0) -> Any:
        with self._lock:
            if self._sock is None:
                self._connect()
            req = json.dumps({'id': self._next_id(), 'method': method, 'params': params or {}})
            old_timeout = self._sock.gettimeout()
            self._sock.settimeout(timeout)
            try:
                try:
                    response = self._send_recv(req)
                except OSError:
                    # Reconnect once on broken pipe
                    self._sock = None
                    self._connect()
                    self._sock.settimeout(timeout)
                    response = self._send_recv(req)
            finally:
                if self._sock is not None:
                    self._sock.settimeout(old_timeout)

        data = json.loads(response)
        if 'error' in data:
            raise RuntimeError(data['error'])
        return data.get('result', {})

    def _recv_line(self) -> str:
        buf = b''
        while b'\n' not in buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise OSError('Connection closed by Natron')
            buf += chunk
        line, _ = buf.split(b'\n', 1)
        return line.decode()


_client = _NatronClient(NATRON_HOST, NATRON_PORT)


def _natron(method: str, _timeout: float = 10.0, **params) -> Any:
    return _client.call(method, params, timeout=_timeout)


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def ping() -> dict:
    """Check connectivity to the Natron TCP server."""
    return _natron('ping')


@mcp.tool()
def get_scene_info() -> dict:
    """Get current Natron project info: name, frame rate, frame range, node count."""
    return _natron('get_scene_info')


@mcp.tool()
def list_nodes() -> dict:
    """List all nodes in the current Natron project graph."""
    return _natron('list_nodes')


@mcp.tool()
def create_node(plugin_id: str) -> dict:
    """
    Create a new node in the Natron project.

    Args:
        plugin_id: Natron plugin ID, e.g. 'fr.inria.built-in.Group',
                   'fr.inria.built-in.Merge', 'net.sf.openfx.GradePlugin'
                   Use list_plugin_ids() to discover available IDs.
    """
    return _natron('create_node', plugin_id=plugin_id)


@mcp.tool()
def get_node_info(script_name: str) -> dict:
    """
    Get details about a node: plugin ID, inputs, and parameter names.

    Args:
        script_name: The node's script name (e.g. 'Merge1')
    """
    return _natron('get_node_info', script_name=script_name)


@mcp.tool()
def get_parameter(node: str, param: str) -> dict:
    """
    Get the current value of a node parameter.

    Args:
        node:  Script name of the node (e.g. 'Grade1')
        param: Script name of the parameter (e.g. 'multiply')
    """
    return _natron('get_parameter', node=node, param=param)


@mcp.tool()
def set_parameter(node: str, param: str, value: Any) -> dict:
    """
    Set a node parameter value.

    Args:
        node:  Script name of the node (e.g. 'Grade1')
        param: Script name of the parameter (e.g. 'multiply')
        value: New value (int, float, str, list depending on param type)
    """
    return _natron('set_parameter', node=node, param=param, value=value)


@mcp.tool()
def connect_nodes(src: str, dst: str, input_index: int = 0) -> dict:
    """
    Connect src node's output to dst node's input.

    Args:
        src:         Script name of the source (upstream) node
        dst:         Script name of the destination (downstream) node
        input_index: Which input slot on dst to connect to (default 0)
    """
    return _natron('connect_nodes', src=src, dst=dst, input_index=input_index)


@mcp.tool()
def delete_node(script_name: str) -> dict:
    """
    Delete a node from the project.

    Args:
        script_name: Script name of the node to delete
    """
    return _natron('delete_node', script_name=script_name)


@mcp.tool()
def execute_python(code: str) -> dict:
    """
    Execute arbitrary Python code inside Natron's embedded interpreter.

    The code runs in Natron's __main__ namespace (same as the Script Editor).
    Set '_result' in the code to return a value, e.g.:
        _result = app1.getProjectParam('projectName').getValue()

    Args:
        code: Python source code to execute
    """
    return _natron('execute_python', code=code)


@mcp.tool()
def save_project(filename: str = '') -> dict:
    """
    Save the current Natron project.

    Args:
        filename: Path to save to. If empty, saves to the current project path
                  (or prompts in GUI mode if never saved before).
    """
    return _natron('save_project', filename=filename)


@mcp.tool()
def load_project(filename: str) -> dict:
    """
    Open a Natron project file (.ntp), replacing the current project.

    Args:
        filename: Absolute path to the .ntp project file
    """
    return _natron('load_project', filename=filename)


@mcp.tool()
def get_frame() -> dict:
    """Get the current timeline frame."""
    return _natron('get_frame')


@mcp.tool()
def set_frame(frame: int) -> dict:
    """
    Seek the timeline to a specific frame. Requires a Viewer node in the project
    and GUI mode (not NatronRenderer).

    Args:
        frame: Frame number to seek to
    """
    return _natron('set_frame', frame=frame)


@mcp.tool()
def set_project_settings(
    fps: float | None = None,
    first_frame: int | None = None,
    last_frame: int | None = None,
) -> dict:
    """
    Set project-level settings. Pass only the values you want to change.

    Args:
        fps:         Frames per second (e.g. 24.0, 25.0, 30.0)
        first_frame: First frame of the project frame range
        last_frame:  Last frame of the project frame range
    """
    p: dict = {}
    if fps is not None:
        p['fps'] = fps
    if first_frame is not None:
        p['first_frame'] = first_frame
    if last_frame is not None:
        p['last_frame'] = last_frame
    return _natron('set_project_settings', **p)


@mcp.tool()
def set_node_position(script_name: str, x: float, y: float) -> dict:
    """
    Set a node's position in the node graph. Returns the actual position after setting.

    Args:
        script_name: Script name of the node (e.g. 'Merge1')
        x:           Horizontal position
        y:           Vertical position
    """
    return _natron('set_node_position', script_name=script_name, x=x, y=y)


@mcp.tool()
def set_node_label(script_name: str, label: str) -> dict:
    """
    Set a node's display label (does not change the script name).

    Args:
        script_name: Script name of the node
        label:       New display label
    """
    return _natron('set_node_label', script_name=script_name, label=label)


@mcp.tool()
def set_node_color(script_name: str, r: float, g: float, b: float) -> dict:
    """
    Set a node's tile color. Returns the actual color after setting.

    Args:
        script_name: Script name of the node
        r:           Red component (0.0–1.0)
        g:           Green component (0.0–1.0)
        b:           Blue component (0.0–1.0)
    """
    return _natron('set_node_color', script_name=script_name, r=r, g=g, b=b)


@mcp.tool()
def render(
    write_node: str,
    first_frame: int,
    last_frame: int,
    frame_step: int = 1,
) -> dict:
    """
    Render frames via a Write node. Blocking in background mode; fire-and-forget in GUI mode.

    Args:
        write_node:  Script name of the Write node to render from
        first_frame: First frame to render (inclusive)
        last_frame:  Last frame to render (inclusive)
        frame_step:  Frame increment (default 1; use 2 to render every other frame)
    """
    return _natron(
        'render',
        write_node=write_node,
        first_frame=first_frame,
        last_frame=last_frame,
        frame_step=frame_step,
    )


@mcp.tool()
def monitor_render(
    output_path: str,
    timeout: int = 3600,
    poll_interval: int = 5,
) -> dict:
    """
    Poll the filesystem until an output file appears (or timeout is reached).
    No Natron connection needed — call this after render() to wait for completion.

    In GUI mode render() returns immediately (non-blocking), so use this tool
    to detect when Natron has actually written the output file.

    Args:
        output_path:   Absolute path to the expected output file (or first frame
                       of a sequence, e.g. '/tmp/out.0001.exr')
        timeout:       Seconds to wait before giving up (default 3600)
        poll_interval: Seconds between filesystem checks (default 5)
    """
    start = time.monotonic()
    while True:
        if os.path.exists(output_path):
            stat = os.stat(output_path)
            elapsed = time.monotonic() - start
            return {
                'found': True,
                'path': output_path,
                'size_bytes': stat.st_size,
                'elapsed_s': round(elapsed, 1),
            }
        elapsed = time.monotonic() - start
        if elapsed >= timeout:
            return {
                'found': False,
                'path': output_path,
                'elapsed_s': round(elapsed, 1),
                'reason': f'timeout after {timeout}s',
            }
        time.sleep(poll_interval)


@mcp.tool()
def create_backdrop(label: str = '') -> dict:
    """
    Create a BackDrop node for grouping and annotating nodes in the graph.

    Args:
        label: Text to display on the backdrop (optional)
    """
    return _natron('create_backdrop', label=label)


@mcp.tool()
def list_plugin_ids(filter: str = '') -> dict:
    """
    List all available Natron plugin IDs.

    Args:
        filter: Optional substring filter (case-insensitive), e.g. 'merge'
                returns only IDs containing 'merge'. Empty returns all.
    """
    return _natron('list_plugin_ids', filter=filter)


@mcp.tool()
def modify_node(node: str, params: dict) -> dict:
    """
    Set multiple parameters on a node in one call (avoids N round-trips).

    Args:
        node:   Script name of the node (e.g. 'Grade1')
        params: Dict mapping parameter script names to new values,
                e.g. {'multiply': 1.2, 'gamma': 0.9}
    """
    return _natron('modify_node', node=node, params=params)


@mcp.tool()
def find_nodes_by_type(plugin_id: str) -> dict:
    """
    Find all nodes of a given plugin type in the project.

    Args:
        plugin_id: Natron plugin ID to search for (e.g. 'fr.inria.built-in.Merge')
    """
    return _natron('find_nodes_by_type', plugin_id=plugin_id)


@mcp.tool()
def batch_set_knob(nodes: list[str], param: str, value: Any) -> dict:
    """
    Set the same parameter to the same value on multiple nodes.

    Args:
        nodes: List of node script names
        param: Parameter script name to set on each node
        value: Value to set (must be compatible with the parameter type)
    """
    return _natron('batch_set_knob', nodes=nodes, param=param, value=value)


@mcp.tool()
def get_expression(node: str, param: str, dimension: int = 0) -> dict:
    """
    Read the current Python expression on a node parameter dimension.

    Returns the expression string and whether it uses a 'return' statement.
    Returns an empty expression string if no expression is set.

    Args:
        node:      Script name of the node (e.g. 'Grade1')
        param:     Script name of the parameter (e.g. 'multiply')
        dimension: Parameter dimension to query (default 0)
    """
    return _natron('get_expression', node=node, param=param, dimension=dimension)


@mcp.tool()
def clear_expression(node: str, param: str, dimension: int = 0) -> dict:
    """
    Remove the Python expression from a node parameter dimension,
    restoring it to a plain value.

    Args:
        node:      Script name of the node (e.g. 'Grade1')
        param:     Script name of the parameter (e.g. 'multiply')
        dimension: Parameter dimension to clear (default 0)
    """
    return _natron('clear_expression', node=node, param=param, dimension=dimension)


@mcp.tool()
def set_expression(
    node: str,
    param: str,
    expression: str,
    dimension: int = 0,
    has_return_var: bool = False,
) -> dict:
    """
    Set a Python expression on a node parameter dimension.

    The expression is evaluated by Natron's Python engine each frame. Use
    `thisNode`, `thisParam`, `frame`, and `dimension` as built-in variables.

    Args:
        node:           Script name of the node (e.g. 'Grade1')
        param:          Script name of the parameter (e.g. 'multiply')
        expression:     Python expression string, e.g. 'frame / 100.0'
        dimension:      Parameter dimension to set (0=default, or R/G/B/A channel)
        has_return_var: Set True if the expression uses 'return' (multi-line body);
                        False (default) for single-expression strings like 'frame * 2'
    """
    return _natron(
        'set_expression',
        node=node,
        param=param,
        expression=expression,
        dimension=dimension,
        has_return_var=has_return_var,
    )


@mcp.tool()
def setup_write_node(file_path: str, src: str = '') -> dict:
    """
    Create a Write node and optionally connect it to an upstream node.
    The encoder is chosen automatically from the file extension.

    Args:
        file_path: Output file path (e.g. '/tmp/render/out.####.exr')
        src:       Script name of the upstream node to connect (optional)
    """
    return _natron('setup_write_node', file_path=file_path, src=src)


# ---------------------------------------------------------------------------
# Documentation tools (BM25 search — no Natron connection needed)
# ---------------------------------------------------------------------------

@mcp.tool()
def search_docs(query: str, top_k: int = 5) -> list:
    """
    Search Natron's offline documentation using BM25.

    Returns up to top_k results as [{'path': str, 'title': str, 'score': float}, ...].
    Requires the docs index to have been built first (scripts/fetch_natron_docs.py).

    Args:
        query: Search terms, e.g. 'Merge node blend modes'
        top_k: Maximum number of results to return (default 5)
    """
    return natron_rag.search_docs(query, top_k)


@mcp.tool()
def get_doc(path: str) -> str:
    """
    Return the full text of a Natron documentation page.

    Use search_docs() first to find a relevant page, then pass its 'path'
    field here to read the full content.

    Args:
        path: Relative path as returned by search_docs (e.g. 'plugins/net.sf.openfx.MergePlugin.html')
    """
    return natron_rag.get_doc(path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == '__main__':
    main()
