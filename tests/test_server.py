"""
test_server.py — Unit tests for src/natronmcp/server.py

Runs without Natron. Patches NatronEngine and PySide so imports succeed.
"""

import json
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Stub NatronEngine and PySide before importing server
# ---------------------------------------------------------------------------

def _make_natron_engine():
    mod = types.ModuleType('NatronEngine')
    mod.natron = MagicMock()
    mod.natron.getNatronVersionString.return_value = '2.5.0'
    return mod


def _make_pyside():
    pyside = types.ModuleType('PySide')
    qtcore = types.ModuleType('PySide.QtCore')
    qtcore.QTimer = MagicMock()
    pyside.QtCore = qtcore
    return pyside, qtcore


_pyside, _qtcore = _make_pyside()
sys.modules.setdefault('NatronEngine', _make_natron_engine())
sys.modules.setdefault('PySide', _pyside)
sys.modules.setdefault('PySide.QtCore', _qtcore)

import importlib
import sys as _sys
# Ensure src/ is on the path
from pathlib import Path
_src = str(Path(__file__).parent.parent / 'src')
if _src not in sys.path:
    sys.path.insert(0, _src)

from natronmcp import server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app(nodes=None):
    app = MagicMock()
    app.getChildren.return_value = nodes or []
    return app


def _make_node(script_name='Node1', label='Node 1', plugin_id='fr.inria.built-in.Merge'):
    node = MagicMock()
    node.getScriptName.return_value = script_name
    node.getLabel.return_value = label
    node.getPluginID.return_value = plugin_id
    node.getMaxInputCount.return_value = 2
    node.getInput.return_value = None
    node.getParams.return_value = []
    return node


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPing(unittest.TestCase):
    def test_returns_ok(self):
        result = server._cmd_ping({})
        self.assertEqual(result['status'], 'ok')

    def test_returns_version(self):
        result = server._cmd_ping({})
        self.assertIn('natron_version', result)


class TestGetSceneInfo(unittest.TestCase):
    def test_returns_scene_fields(self):
        app = _make_app()
        proj = MagicMock()
        proj.return_value = MagicMock()
        proj.return_value.getValue.return_value = 'test.ntp'
        app.getProjectParam = proj
        # Override getValue per param
        def _proj(name):
            m = MagicMock()
            m.getValue.return_value = {'projectName': 'test.ntp', 'frameRate': 24.0,
                                        'firstFrame': 1, 'lastFrame': 100}.get(name, '')
            return m
        app.getProjectParam = _proj

        with patch.object(server, '_require_app', return_value=app):
            result = server._cmd_get_scene_info({})

        self.assertIn('node_count', result)
        self.assertIn('frame_range', result)


class TestListNodes(unittest.TestCase):
    def test_empty_project(self):
        app = _make_app(nodes=[])
        with patch.object(server, '_require_app', return_value=app):
            result = server._cmd_list_nodes({})
        self.assertEqual(result['nodes'], [])

    def test_with_nodes(self):
        node = _make_node('Grade1', 'Grade 1', 'fr.inria.built-in.Grade')
        app = _make_app(nodes=[node])
        with patch.object(server, '_require_app', return_value=app):
            result = server._cmd_list_nodes({})
        self.assertEqual(len(result['nodes']), 1)
        self.assertEqual(result['nodes'][0]['script_name'], 'Grade1')


class TestCreateNode(unittest.TestCase):
    def test_missing_plugin_id(self):
        with self.assertRaises(ValueError):
            server._cmd_create_node({})

    def test_creates_node(self):
        node = _make_node('Grade1')
        app = _make_app()
        app.createNode.return_value = node
        with patch.object(server, '_require_app', return_value=app):
            result = server._cmd_create_node({'plugin_id': 'fr.inria.built-in.Grade'})
        self.assertEqual(result['script_name'], 'Grade1')

    def test_failed_create_raises(self):
        app = _make_app()
        app.createNode.return_value = None
        with patch.object(server, '_require_app', return_value=app):
            with self.assertRaises(RuntimeError):
                server._cmd_create_node({'plugin_id': 'bad.plugin'})


class TestGetNodeInfo(unittest.TestCase):
    def test_missing_script_name(self):
        with self.assertRaises(ValueError):
            server._cmd_get_node_info({})

    def test_node_not_found(self):
        app = _make_app()
        app.getNode.return_value = None
        with patch.object(server, '_require_app', return_value=app):
            with self.assertRaises(RuntimeError):
                server._cmd_get_node_info({'script_name': 'Missing1'})

    def test_returns_info(self):
        node = _make_node('Merge1')
        app = _make_app()
        app.getNode.return_value = node
        with patch.object(server, '_require_app', return_value=app):
            result = server._cmd_get_node_info({'script_name': 'Merge1'})
        self.assertEqual(result['script_name'], 'Merge1')
        self.assertIn('inputs', result)
        self.assertIn('params', result)


class TestConnectNodes(unittest.TestCase):
    def test_missing_args(self):
        with self.assertRaises(ValueError):
            server._cmd_connect_nodes({'src': 'A'})

    def test_connect(self):
        src = _make_node('Read1')
        dst = _make_node('Grade1')
        dst.connectInput.return_value = True
        app = _make_app()
        def _get_node(name):
            return {'Read1': src, 'Grade1': dst}[name]
        app.getNode.side_effect = _get_node
        with patch.object(server, '_require_app', return_value=app):
            result = server._cmd_connect_nodes({'src': 'Read1', 'dst': 'Grade1', 'input_index': 0})
        self.assertTrue(result['ok'])
        dst.connectInput.assert_called_once_with(0, src)


class TestDeleteNode(unittest.TestCase):
    def test_missing_script_name(self):
        with self.assertRaises(ValueError):
            server._cmd_delete_node({})

    def test_delete(self):
        node = _make_node('Grade1')
        app = _make_app()
        app.getNode.return_value = node
        with patch.object(server, '_require_app', return_value=app):
            result = server._cmd_delete_node({'script_name': 'Grade1'})
        node.destroy.assert_called_once()
        self.assertEqual(result['deleted'], 'Grade1')


class TestExecutePython(unittest.TestCase):
    def test_missing_code(self):
        with self.assertRaises(ValueError):
            server._cmd_execute_python({})

    def test_captures_stdout(self):
        result = server._cmd_execute_python({'code': 'print("hello")'})
        self.assertIn('hello', result['output'])

    def test_result_var(self):
        result = server._cmd_execute_python({'code': '_result = 42'})
        self.assertEqual(result['result'], 42)


class TestDispatch(unittest.TestCase):
    def test_unknown_method(self):
        with self.assertRaises(ValueError):
            # dispatch non-main-thread methods via _run_on_main_thread, but
            # unknown method raises before that
            server._dispatch('no_such_method', {})

    def test_ping_inline(self):
        result = server._dispatch('ping', {})
        self.assertEqual(result['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
