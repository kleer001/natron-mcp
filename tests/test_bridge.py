"""
test_bridge.py — Unit tests for natron_mcp_server.py

Patches _NatronClient so no TCP connection is made. Verifies that MCP
tool functions call the right methods with the right arguments.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure repo root is importable
_root = str(Path(__file__).parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import natron_mcp_server as bridge
import natron_rag


def _mock_client(return_value=None):
    client = MagicMock()
    client.call.return_value = return_value or {'status': 'ok'}
    return client


# ---------------------------------------------------------------------------
# ping
# ---------------------------------------------------------------------------

def test_ping_calls_ping():
    with patch.object(bridge, '_client', _mock_client({'status': 'ok', 'natron_version': '2.5.0'})):
        result = bridge.ping()
    assert result['status'] == 'ok'


# ---------------------------------------------------------------------------
# get_scene_info
# ---------------------------------------------------------------------------

def test_get_scene_info():
    payload = {'project_name': 'test', 'frame_rate': 24.0, 'frame_range': [1, 100], 'node_count': 3}
    with patch.object(bridge, '_client', _mock_client(payload)):
        result = bridge.get_scene_info()
    assert result['node_count'] == 3


# ---------------------------------------------------------------------------
# list_nodes
# ---------------------------------------------------------------------------

def test_list_nodes():
    payload = {'nodes': [{'script_name': 'Grade1', 'label': 'Grade', 'plugin_id': 'x'}]}
    with patch.object(bridge, '_client', _mock_client(payload)):
        result = bridge.list_nodes()
    assert len(result['nodes']) == 1


# ---------------------------------------------------------------------------
# create_node
# ---------------------------------------------------------------------------

def test_create_node():
    payload = {'script_name': 'Grade1', 'label': 'Grade 1', 'plugin_id': 'fr.inria.built-in.Grade'}
    mock = _mock_client(payload)
    with patch.object(bridge, '_client', mock):
        result = bridge.create_node('fr.inria.built-in.Grade')
    assert result['script_name'] == 'Grade1'
    mock.call.assert_called_once_with('create_node', {'plugin_id': 'fr.inria.built-in.Grade'})


# ---------------------------------------------------------------------------
# get_parameter / set_parameter
# ---------------------------------------------------------------------------

def test_get_parameter():
    payload = {'node': 'Grade1', 'param': 'multiply', 'value': 1.0}
    with patch.object(bridge, '_client', _mock_client(payload)):
        result = bridge.get_parameter('Grade1', 'multiply')
    assert result['value'] == 1.0


def test_set_parameter():
    payload = {'ok': True, 'node': 'Grade1', 'param': 'multiply', 'value': 2.0}
    mock = _mock_client(payload)
    with patch.object(bridge, '_client', mock):
        result = bridge.set_parameter('Grade1', 'multiply', 2.0)
    assert result['ok'] is True
    mock.call.assert_called_once_with(
        'set_parameter', {'node': 'Grade1', 'param': 'multiply', 'value': 2.0}
    )


# ---------------------------------------------------------------------------
# connect_nodes
# ---------------------------------------------------------------------------

def test_connect_nodes():
    payload = {'ok': True, 'src': 'Read1', 'dst': 'Grade1', 'input_index': 0}
    with patch.object(bridge, '_client', _mock_client(payload)):
        result = bridge.connect_nodes('Read1', 'Grade1', 0)
    assert result['ok'] is True


# ---------------------------------------------------------------------------
# delete_node
# ---------------------------------------------------------------------------

def test_delete_node():
    payload = {'ok': True, 'deleted': 'Grade1'}
    with patch.object(bridge, '_client', _mock_client(payload)):
        result = bridge.delete_node('Grade1')
    assert result['deleted'] == 'Grade1'


# ---------------------------------------------------------------------------
# execute_python
# ---------------------------------------------------------------------------

def test_execute_python():
    payload = {'output': 'hello\n', 'result': None}
    with patch.object(bridge, '_client', _mock_client(payload)):
        result = bridge.execute_python('print("hello")')
    assert 'hello' in result['output']


# ---------------------------------------------------------------------------
# search_docs / get_doc (RAG tools — no TCP connection)
# ---------------------------------------------------------------------------

def test_search_docs_delegates_to_rag():
    hits = [{'path': 'plugins/Merge.html', 'title': 'Merge', 'score': 3.14}]
    with patch.object(natron_rag, 'search_docs', return_value=hits) as mock_search:
        result = bridge.search_docs('merge blend', top_k=3)
    assert result == hits
    mock_search.assert_called_once_with('merge blend', 3)


def test_search_docs_empty_query_returns_empty():
    with patch.object(natron_rag, 'search_docs', return_value=[]):
        result = bridge.search_docs('')
    assert result == []


def test_get_doc_delegates_to_rag():
    with patch.object(natron_rag, 'get_doc', return_value='Merge documentation text') as mock_get:
        result = bridge.get_doc('plugins/Merge.html')
    assert 'Merge' in result
    mock_get.assert_called_once_with('plugins/Merge.html')


def test_get_doc_missing_raises():
    with patch.object(natron_rag, 'get_doc', side_effect=FileNotFoundError('not found')):
        with pytest.raises(FileNotFoundError):
            bridge.get_doc('nonexistent.html')


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------

def test_error_propagates():
    client = MagicMock()
    client.call.side_effect = RuntimeError('Node not found: Bad1')
    with patch.object(bridge, '_client', client):
        with pytest.raises(RuntimeError, match='Node not found'):
            bridge.get_node_info('Bad1')
