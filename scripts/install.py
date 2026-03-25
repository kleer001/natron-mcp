#!/usr/bin/env python3
"""
install.py — Set up natronmcp for automatic loading in Natron.

This script:
  1. Appends a startup block to ~/.Natron/init.py so Natron loads the MCP
     TCP server automatically.
  2. (Linux only) Installs a .desktop entry and icon so Natron appears in
     KDE/GNOME launchers, then refreshes the desktop database.

Usage:
    python scripts/install.py
    python scripts/install.py --natron-dir /path/to/natronmcp/src
    python scripts/install.py --natron-install-dir /path/to/Natron/install
    python scripts/install.py --dry-run
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from natron_detect import find_natron_install

INIT_PY = Path.home() / '.Natron' / 'init.py'
MARKER  = '# natron-mcp auto-start'

_DESKTOP_TEMPLATE = """\
[Desktop Entry]
Version=1.0
Type=Application
Name=Natron
GenericName=Visual Effects Compositor
Comment=Open-source compositing software for VFX and motion graphics
Exec={binary} %F
Icon=natron
Terminal=false
Categories=Graphics;Video;2DGraphics;
MimeType=application/x-natron;
Keywords=vfx;compositing;visual effects;nuke;natron;
StartupNotify=true
StartupWMClass=Natron
"""


def install_desktop_entry(install_dir: Path, dry_run: bool = False):
    """Install a .desktop file and icon for Natron (Linux only)."""
    if not sys.platform.startswith('linux'):
        return

    binary = install_dir / 'Natron'
    if not binary.exists():
        print(f'Warning: Natron binary not found at {binary} — skipping desktop entry')
        return

    # .desktop file
    desktop_dir = Path.home() / '.local' / 'share' / 'applications'
    desktop_file = desktop_dir / 'natron.desktop'
    content = _DESKTOP_TEMPLATE.format(binary=str(binary))

    print(f'Desktop entry: {desktop_file}')
    if not dry_run:
        desktop_dir.mkdir(parents=True, exist_ok=True)
        desktop_file.write_text(content)

    # Icon — copy from Natron's bundled pixmaps if available
    icon_src = install_dir / 'Resources' / 'pixmaps' / 'natronIcon256_linux.png'
    icon_dst = Path.home() / '.local' / 'share' / 'icons' / 'hicolor' / '256x256' / 'apps' / 'natron.png'
    if icon_src.exists():
        print(f'Icon: {icon_dst}')
        if not dry_run:
            icon_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(icon_src), str(icon_dst))
    else:
        print(f'Warning: icon not found at {icon_src} — desktop entry will use system icon theme')

    if dry_run:
        print('Dry run — no desktop files written.')
        return

    # Refresh desktop and icon databases
    for cmd in (
        ['update-desktop-database', str(desktop_dir)],
        ['gtk-update-icon-cache', '-f', '-t',
         str(Path.home() / '.local' / 'share' / 'icons' / 'hicolor')],
    ):
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass  # tools may not be present; non-fatal

    print('Desktop entry installed.')


def install(src_dir: Path, dry_run: bool = False):
    lines = [
        f'{MARKER}',
        f'import sys',
        f'sys.path.insert(0, {str(src_dir)!r})',
        f'import natronmcp',
        f'natronmcp.start()',
    ]
    block = '\n'.join(lines) + '\n'

    existing = ''
    if INIT_PY.exists():
        existing = INIT_PY.read_text()

    if MARKER in existing:
        print(f'natron-mcp block already present in {INIT_PY}')
        return

    print(f'Target: {INIT_PY}')
    print(f'Will append:\n{block}')

    if dry_run:
        print('Dry run — no changes made.')
        return

    INIT_PY.parent.mkdir(parents=True, exist_ok=True)
    with open(INIT_PY, 'a') as f:
        if existing and not existing.endswith('\n'):
            f.write('\n')
        f.write(block)

    print('Done. Restart Natron for changes to take effect.')


def main():
    repo_root = Path(__file__).parent.parent
    default_src = repo_root / 'src'

    parser = argparse.ArgumentParser(
        description='Install natronmcp startup hook and (Linux) desktop entry')
    parser.add_argument('--natron-dir', default=str(default_src),
                        help=f'Path to the natronmcp src/ directory (default: {default_src})')
    parser.add_argument('--natron-install-dir', default=None,
                        help='Natron install directory for desktop entry (default: auto-detected)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without writing any files')
    args = parser.parse_args()

    src_dir = Path(args.natron_dir).resolve()
    if not (src_dir / 'natronmcp').is_dir():
        print(f'Error: {src_dir}/natronmcp not found. Check --natron-dir.', file=sys.stderr)
        sys.exit(1)

    install(src_dir, args.dry_run)

    # Desktop entry (Linux only)
    if sys.platform.startswith('linux'):
        if args.natron_install_dir:
            natron_dir = Path(args.natron_install_dir)
        else:
            natron_dir = find_natron_install()
        if natron_dir:
            install_desktop_entry(natron_dir, args.dry_run)
        else:
            print('Natron not found — skipping desktop entry. '
                  'Use --natron-install-dir to specify the install path.')


if __name__ == '__main__':
    main()
