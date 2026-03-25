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
import socket
import threading
from typing import Any

from mcp.server.fastmcp import FastMCP

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

    def call(self, method: str, params: dict | None = None) -> Any:
        with self._lock:
            if self._sock is None:
                self._connect()
            req = json.dumps({'id': self._next_id(), 'method': method, 'params': params or {}})
            try:
                response = self._send_recv(req)
            except OSError:
                # Reconnect once on broken pipe
                self._sock = None
                self._connect()
                response = self._send_recv(req)

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


def _natron(method: str, **params) -> Any:
    return _client.call(method, params)


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
        plugin_id: Natron plugin ID, e.g. 'fr.inria.openfx.ReadOIIO',
                   'fr.inria.built-in.Merge', 'fr.inria.built-in.Grade'
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == '__main__':
    main()
