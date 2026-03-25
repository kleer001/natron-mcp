"""
test_scripts.py — Tests for scripts/natron_detect.py, install.py,
                  fetch_natron_docs.py, and launch.py.

All tests use tmp_path and mocks so nothing touches the real filesystem,
real Natron install, or real home directory.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_root = Path(__file__).parent.parent
_scripts = _root / 'scripts'
for _p in (str(_root), str(_scripts)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import natron_detect
import install as install_mod
import fetch_natron_docs as fetch_mod
import launch as launch_mod


# ===========================================================================
# natron_detect — find_natron_install
# ===========================================================================

class TestFindNatronInstall:
    def test_found_via_path(self, tmp_path):
        binary = tmp_path / 'Natron'
        binary.touch()
        with patch.object(natron_detect.shutil, 'which', return_value=str(binary)):
            result = natron_detect.find_natron_install()
        assert result == tmp_path.resolve()

    def test_found_via_xdg_desktop_file(self, tmp_path):
        binary = tmp_path / 'Natron'
        binary.touch()
        app_dir = tmp_path / 'applications'
        app_dir.mkdir()
        (app_dir / 'natron.desktop').write_text(
            f'[Desktop Entry]\nExec={binary} %F\nType=Application\n'
        )
        with patch.object(natron_detect.shutil, 'which', return_value=None), \
             patch.dict('os.environ', {'XDG_DATA_DIRS': str(tmp_path)}, clear=False), \
             patch('pathlib.Path.home', return_value=tmp_path / 'nohome'):
            result = natron_detect.find_natron_install()
        assert result == tmp_path.resolve()

    def test_desktop_file_ignores_non_natron_binary(self, tmp_path):
        """Exec= pointing to a binary not named Natron should not match."""
        other = tmp_path / 'SomethingElse'
        other.touch()
        app_dir = tmp_path / 'applications'
        app_dir.mkdir()
        (app_dir / 'natron.desktop').write_text(
            f'[Desktop Entry]\nExec={other} %F\n'
        )
        with patch.object(natron_detect.shutil, 'which', return_value=None), \
             patch.dict('os.environ', {'XDG_DATA_DIRS': str(tmp_path)}, clear=False), \
             patch('pathlib.Path.home', return_value=tmp_path / 'nohome'):
            result = natron_detect.find_natron_install()
        assert result is None

    def test_returns_none_when_nothing_found(self, tmp_path):
        with patch.object(natron_detect.shutil, 'which', return_value=None), \
             patch('pathlib.Path.home', return_value=tmp_path), \
             patch.dict('os.environ', {'XDG_DATA_DIRS': ''}, clear=False):
            result = natron_detect.find_natron_install()
        assert result is None


# ===========================================================================
# natron_detect — get_natron_version
# ===========================================================================

class TestGetNatronVersion:
    def test_parses_version_from_directory_name(self, tmp_path):
        install_dir = tmp_path / 'Natron-2.5.0-Linux-x86_64-no-installer'
        install_dir.mkdir()
        result = natron_detect.get_natron_version(install_dir)
        assert result == '2.5.0'

    def test_parses_version_from_subprocess_output(self, tmp_path):
        binary = tmp_path / 'Natron'
        binary.touch()
        mock_result = MagicMock()
        mock_result.stdout = 'Natron version 2.5.0\n'
        mock_result.stderr = ''
        with patch.object(natron_detect.subprocess, 'run', return_value=mock_result):
            result = natron_detect.get_natron_version(tmp_path)
        assert result == '2.5.0'

    def test_subprocess_version_takes_precedence_over_dir_name(self, tmp_path):
        install_dir = tmp_path / 'Natron-2.4.0-old'
        install_dir.mkdir()
        binary = install_dir / 'Natron'
        binary.touch()
        mock_result = MagicMock()
        mock_result.stdout = 'Natron 2.5.1\n'
        mock_result.stderr = ''
        with patch.object(natron_detect.subprocess, 'run', return_value=mock_result):
            result = natron_detect.get_natron_version(install_dir)
        assert result == '2.5.1'

    def test_falls_back_to_dir_name_when_subprocess_raises(self, tmp_path):
        install_dir = tmp_path / 'Natron-2.5.0-Linux'
        install_dir.mkdir()
        binary = install_dir / 'Natron'
        binary.touch()
        with patch.object(natron_detect.subprocess, 'run', side_effect=Exception('fail')):
            result = natron_detect.get_natron_version(install_dir)
        assert result == '2.5.0'

    def test_returns_none_when_nothing_works(self, tmp_path):
        install_dir = tmp_path / 'SomeRandomDir'
        install_dir.mkdir()
        with patch.object(natron_detect.subprocess, 'run', side_effect=Exception('fail')):
            result = natron_detect.get_natron_version(install_dir)
        assert result is None


# ===========================================================================
# install — init.py hook
# ===========================================================================

class TestInstallHook:
    def test_appends_block_to_new_file(self, tmp_path):
        init_py = tmp_path / 'init.py'
        src_dir = tmp_path / 'src'
        with patch.object(install_mod, 'INIT_PY', init_py):
            install_mod.install(src_dir)
        assert init_py.exists()
        content = init_py.read_text()
        assert install_mod.MARKER in content
        assert 'import natronmcp' in content
        assert 'natronmcp.start()' in content

    def test_appends_to_existing_file(self, tmp_path):
        init_py = tmp_path / 'init.py'
        init_py.write_text('# existing content\n')
        src_dir = tmp_path / 'src'
        with patch.object(install_mod, 'INIT_PY', init_py):
            install_mod.install(src_dir)
        content = init_py.read_text()
        assert '# existing content' in content
        assert install_mod.MARKER in content

    def test_skips_when_marker_already_present(self, tmp_path):
        init_py = tmp_path / 'init.py'
        init_py.write_text(f'{install_mod.MARKER}\nimport natronmcp\nnatronmcp.start()\n')
        src_dir = tmp_path / 'src'
        with patch.object(install_mod, 'INIT_PY', init_py):
            install_mod.install(src_dir)
        assert init_py.read_text().count(install_mod.MARKER) == 1

    def test_dry_run_does_not_write(self, tmp_path):
        init_py = tmp_path / 'init.py'
        src_dir = tmp_path / 'src'
        with patch.object(install_mod, 'INIT_PY', init_py):
            install_mod.install(src_dir, dry_run=True)
        assert not init_py.exists()


# ===========================================================================
# install — Linux desktop entry
# ===========================================================================

class TestInstallLinuxEntry:
    def _make_install_dir(self, tmp_path):
        install_dir = tmp_path / 'Natron-install'
        install_dir.mkdir()
        (install_dir / 'Natron').touch()
        pixmaps = install_dir / 'Resources' / 'pixmaps'
        pixmaps.mkdir(parents=True)
        (pixmaps / 'natronIcon256_linux.png').write_bytes(b'\x89PNG\r\n')
        return install_dir

    def test_creates_desktop_file_with_binary_path(self, tmp_path):
        install_dir = self._make_install_dir(tmp_path)
        fake_home = tmp_path / 'home'
        fake_home.mkdir()
        with patch('pathlib.Path.home', return_value=fake_home), \
             patch.object(install_mod.subprocess, 'run'):
            install_mod._install_linux_entry(install_dir)
        desktop = fake_home / '.local' / 'share' / 'applications' / 'natron.desktop'
        assert desktop.exists()
        assert str(install_dir / 'Natron') in desktop.read_text()

    def test_copies_icon(self, tmp_path):
        install_dir = self._make_install_dir(tmp_path)
        fake_home = tmp_path / 'home'
        fake_home.mkdir()
        with patch('pathlib.Path.home', return_value=fake_home), \
             patch.object(install_mod.subprocess, 'run'):
            install_mod._install_linux_entry(install_dir)
        icon = (fake_home / '.local' / 'share' / 'icons'
                / 'hicolor' / '256x256' / 'apps' / 'natron.png')
        assert icon.exists()

    def test_skips_gracefully_when_binary_missing(self, tmp_path, capsys):
        install_mod._install_linux_entry(tmp_path)
        assert 'Warning' in capsys.readouterr().out

    def test_dry_run_writes_nothing(self, tmp_path):
        install_dir = self._make_install_dir(tmp_path)
        fake_home = tmp_path / 'home'
        fake_home.mkdir()
        with patch('pathlib.Path.home', return_value=fake_home):
            install_mod._install_linux_entry(install_dir, dry_run=True)
        assert not (fake_home / '.local').exists()

    def test_runs_database_refresh_commands(self, tmp_path):
        install_dir = self._make_install_dir(tmp_path)
        fake_home = tmp_path / 'home'
        fake_home.mkdir()
        with patch('pathlib.Path.home', return_value=fake_home), \
             patch.object(install_mod.subprocess, 'run') as mock_run:
            install_mod._install_linux_entry(install_dir)
        assert mock_run.call_count == 2


# ===========================================================================
# install — macOS Launch Services
# ===========================================================================

class TestInstallMacOSEntry:
    def _make_app_bundle(self, tmp_path):
        app = tmp_path / 'Natron.app'
        binary_dir = app / 'Contents' / 'MacOS'
        binary_dir.mkdir(parents=True)
        (binary_dir / 'Natron').touch()
        return app, binary_dir

    def test_calls_lsregister_with_app_bundle(self, tmp_path):
        app, binary_dir = self._make_app_bundle(tmp_path)
        with patch.object(install_mod.subprocess, 'run') as mock_run:
            install_mod._install_macos_entry(binary_dir)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert str(app) in cmd

    def test_warns_when_no_app_bundle_ancestor(self, tmp_path, capsys):
        # A flat directory with no .app parent
        install_mod._install_macos_entry(tmp_path)
        assert 'Warning' in capsys.readouterr().out

    def test_dry_run_does_not_call_lsregister(self, tmp_path):
        app, binary_dir = self._make_app_bundle(tmp_path)
        with patch.object(install_mod.subprocess, 'run') as mock_run:
            install_mod._install_macos_entry(binary_dir, dry_run=True)
        mock_run.assert_not_called()


# ===========================================================================
# fetch_natron_docs — build_index
# ===========================================================================

_SAMPLE_HTML = """\
<!DOCTYPE html><html>
<head><title>Merge Node</title></head>
<body><p>The Merge node composites two inputs using blend modes.</p></body>
</html>
"""

_MINIMAL_HTML = """\
<html><head><title>Grade</title></head>
<body><p>Apply colour corrections.</p></body></html>
"""


class TestBuildIndex:
    def _setup(self, tmp_path, extra_files=None):
        docs_dir = tmp_path / 'html'
        docs_dir.mkdir()
        (docs_dir / 'merge.html').write_text(_SAMPLE_HTML)
        for name, content in (extra_files or {}).items():
            (docs_dir / name).write_text(content)
        out_dir = tmp_path / 'out'
        out_dir.mkdir()
        return docs_dir, out_dir

    def test_parses_title_and_writes_index(self, tmp_path):
        docs_dir, out_dir = self._setup(tmp_path)
        fetch_mod.build_index(docs_dir, out_dir)
        idx = json.loads((out_dir / 'natron_docs_index.json').read_text())
        assert idx['N'] == 1
        assert idx['docs'][0]['title'] == 'Merge Node'

    def test_stores_natron_version(self, tmp_path):
        docs_dir, out_dir = self._setup(tmp_path)
        fetch_mod.build_index(docs_dir, out_dir, natron_version='2.5.0')
        idx = json.loads((out_dir / 'natron_docs_index.json').read_text())
        assert idx['natron_version'] == '2.5.0'

    def test_stores_docs_dir_path(self, tmp_path):
        docs_dir, out_dir = self._setup(tmp_path)
        fetch_mod.build_index(docs_dir, out_dir)
        idx = json.loads((out_dir / 'natron_docs_index.json').read_text())
        assert idx['docs_dir'] == str(docs_dir)

    def test_writes_raw_text_files(self, tmp_path):
        docs_dir, out_dir = self._setup(tmp_path)
        fetch_mod.build_index(docs_dir, out_dir)
        txt = out_dir / 'natron_docs' / 'merge.txt'
        assert txt.exists()
        assert 'Merge Node' in txt.read_text()

    def test_indexes_multiple_files(self, tmp_path):
        docs_dir, out_dir = self._setup(tmp_path, {'grade.html': _MINIMAL_HTML})
        fetch_mod.build_index(docs_dir, out_dir)
        idx = json.loads((out_dir / 'natron_docs_index.json').read_text())
        assert idx['N'] == 2

    def test_exits_on_empty_directory(self, tmp_path):
        docs_dir = tmp_path / 'html'
        docs_dir.mkdir()
        out_dir = tmp_path / 'out'
        out_dir.mkdir()
        with pytest.raises(SystemExit):
            fetch_mod.build_index(docs_dir, out_dir)

    def test_version_none_stored_as_null(self, tmp_path):
        docs_dir, out_dir = self._setup(tmp_path)
        fetch_mod.build_index(docs_dir, out_dir, natron_version=None)
        idx = json.loads((out_dir / 'natron_docs_index.json').read_text())
        assert idx['natron_version'] is None


# ===========================================================================
# launch — _most_recent_project
# ===========================================================================

class TestMostRecentProject:
    def test_returns_first_existing_project(self, tmp_path):
        proj = tmp_path / 'my_comp.ntp'
        proj.touch()
        conf = tmp_path / 'Natron.conf'
        conf.write_text(f'recentFileList={proj}\n')
        with patch.object(launch_mod, 'NATRON_CONF', conf):
            result = launch_mod._most_recent_project()
        assert result == str(proj)

    def test_returns_none_when_conf_missing(self, tmp_path):
        with patch.object(launch_mod, 'NATRON_CONF', tmp_path / 'no.conf'):
            result = launch_mod._most_recent_project()
        assert result is None

    def test_returns_none_when_project_file_missing(self, tmp_path):
        conf = tmp_path / 'Natron.conf'
        conf.write_text('recentFileList=/nonexistent/project.ntp\n')
        with patch.object(launch_mod, 'NATRON_CONF', conf):
            result = launch_mod._most_recent_project()
        assert result is None

    def test_returns_none_when_list_empty(self, tmp_path):
        conf = tmp_path / 'Natron.conf'
        conf.write_text('recentFileList=\n')
        with patch.object(launch_mod, 'NATRON_CONF', conf):
            result = launch_mod._most_recent_project()
        assert result is None

    def test_ignores_non_recent_file_lines(self, tmp_path):
        conf = tmp_path / 'Natron.conf'
        conf.write_text('[General]\nversion=2.5.0\n')
        with patch.object(launch_mod, 'NATRON_CONF', conf):
            result = launch_mod._most_recent_project()
        assert result is None


# ===========================================================================
# launch — _ping
# ===========================================================================

class TestPing:
    def test_returns_false_when_no_server(self):
        # Connecting to a port with nothing listening should return False, not raise.
        assert launch_mod._ping(19876) is False

    def test_returns_true_when_server_responds(self, tmp_path):
        """Simulate a server that responds with the expected JSON."""
        import socket
        import threading
        import json as _json

        response = _json.dumps({'result': {'status': 'ok'}}).encode() + b'\n'

        def _serve(sock):
            try:
                conn, _ = sock.accept()
                conn.recv(4096)
                conn.sendall(response)
                conn.close()
            except Exception:
                pass

        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]
        t = threading.Thread(target=_serve, args=(server,), daemon=True)
        t.start()
        result = launch_mod._ping(port)
        server.close()
        assert result is True
