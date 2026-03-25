"""
natron_detect.py — Cross-platform Natron install detection.

Shared by fetch_natron_docs.py and launch.py.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def find_natron_install() -> Path | None:
    """
    Return the directory containing the Natron binary, or None if not found.
    Checks PATH first, then common per-OS install locations.
    """
    # 1. PATH
    binary = shutil.which('Natron')
    if binary:
        return Path(binary).resolve().parent

    platform = sys.platform

    if platform.startswith('linux'):
        for root in (Path('/opt'), Path.home(), Path.home() / '.local'):
            if not root.exists():
                continue
            try:
                for d in root.iterdir():
                    if d.name.startswith('Natron') and (d / 'Natron').exists():
                        return d
            except PermissionError:
                pass

    elif platform == 'darwin':
        for apps in (Path('/Applications'), Path.home() / 'Applications'):
            if not apps.exists():
                continue
            for app in apps.glob('Natron*.app'):
                binary_path = app / 'Contents' / 'MacOS' / 'Natron'
                if binary_path.exists():
                    return binary_path.parent

    elif platform == 'win32':
        for env_var in ('LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)'):
            base = os.environ.get(env_var)
            if not base:
                continue
            base_path = Path(base)
            if not base_path.exists():
                continue
            try:
                for d in base_path.iterdir():
                    if d.name.startswith('Natron') and (d / 'Natron.exe').exists():
                        return d
            except PermissionError:
                pass

    return None


def get_natron_version(install_dir: Path) -> str | None:
    """
    Return the Natron version string (e.g. '2.5.0'), or None.

    Tries two strategies:
    1. Run `Natron --version` and parse the output.
    2. Parse the version from the install directory name
       (e.g. 'Natron-2.5.0-Linux-x86_64-no-installer').
    """
    binary_name = 'Natron.exe' if sys.platform == 'win32' else 'Natron'
    binary = install_dir / binary_name

    if binary.exists():
        try:
            result = subprocess.run(
                [str(binary), '--version'],
                capture_output=True, text=True, timeout=10,
            )
            for line in (result.stdout + result.stderr).splitlines():
                m = re.search(r'(\d+\.\d+\.\d+)', line)
                if m:
                    return m.group(1)
        except Exception:
            pass

    # Fallback: parse from directory name
    m = re.search(r'[Nn]atron[_-](\d+\.\d+[\.\d]*)', install_dir.name)
    if m:
        return m.group(1)

    return None
