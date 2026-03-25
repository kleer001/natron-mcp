#!/usr/bin/env python3
"""
install.py — Set up natronmcp for automatic loading in Natron.

This script:
  1. Appends a startup block to ~/.Natron/init.py so Natron loads the MCP
     TCP server automatically.
  2. Registers Natron with the OS app launcher:
       Linux   — writes ~/.local/share/applications/natron.desktop, copies
                  icon, runs update-desktop-database + gtk-update-icon-cache
       macOS   — registers the .app bundle with Launch Services (Spotlight/Dock)
       Windows — creates a Start Menu shortcut via PowerShell

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


def _install_linux_entry(install_dir: Path, dry_run: bool = False):
    binary = install_dir / 'Natron'
    if not binary.exists():
        print(f'Warning: Natron binary not found at {binary} — skipping desktop entry')
        return

    desktop_dir = Path.home() / '.local' / 'share' / 'applications'
    desktop_file = desktop_dir / 'natron.desktop'
    content = _DESKTOP_TEMPLATE.format(binary=str(binary))
    print(f'Desktop entry: {desktop_file}')
    if not dry_run:
        desktop_dir.mkdir(parents=True, exist_ok=True)
        desktop_file.write_text(content)

    icon_src = install_dir / 'Resources' / 'pixmaps' / 'natronIcon256_linux.png'
    icon_dst = (Path.home() / '.local' / 'share' / 'icons'
                / 'hicolor' / '256x256' / 'apps' / 'natron.png')
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

    for cmd in (
        ['update-desktop-database', str(desktop_dir)],
        ['gtk-update-icon-cache', '-f', '-t',
         str(Path.home() / '.local' / 'share' / 'icons' / 'hicolor')],
    ):
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

    print('Desktop entry installed.')


def _install_macos_entry(install_dir: Path, dry_run: bool = False):
    # install_dir is Contents/MacOS/ when detected from a .app bundle.
    # Walk up to find the .app bundle root.
    app_bundle = install_dir
    for _ in range(3):
        if app_bundle.suffix == '.app':
            break
        app_bundle = app_bundle.parent
    else:
        print(f'Warning: could not locate .app bundle from {install_dir} — skipping Launch Services registration')
        return

    print(f'Registering with Launch Services: {app_bundle}')
    if dry_run:
        print('Dry run — no registration performed.')
        return

    lsregister = (
        '/System/Library/Frameworks/CoreServices.framework'
        '/Frameworks/LaunchServices.framework/Support/lsregister'
    )
    try:
        subprocess.run([lsregister, '-f', str(app_bundle)], check=True, capture_output=True)
        print('Launch Services registration complete.')
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f'Warning: lsregister failed ({e}) — Natron may not appear in Spotlight/Dock immediately')


def _install_windows_entry(install_dir: Path, dry_run: bool = False):
    binary = install_dir / 'Natron.exe'
    if not binary.exists():
        print(f'Warning: Natron.exe not found at {binary} — skipping Start Menu shortcut')
        return

    start_menu = (Path(os.environ.get('APPDATA', ''))
                  / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs')
    shortcut = start_menu / 'Natron.lnk'

    print(f'Start Menu shortcut: {shortcut}')
    if dry_run:
        print('Dry run — no shortcut written.')
        return

    ps_script = (
        f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut({str(shortcut)!r});'
        f'$s.TargetPath = {str(binary)!r};'
        f'$s.IconLocation = {str(binary)!r};'
        f'$s.Description = "Open-source compositing software for VFX and motion graphics";'
        f'$s.Save()'
    )
    try:
        subprocess.run(['powershell', '-NoProfile', '-Command', ps_script],
                       check=True, capture_output=True)
        print('Start Menu shortcut installed.')
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f'Warning: shortcut creation failed ({e})')


def install_os_entry(install_dir: Path, dry_run: bool = False):
    """Register Natron with the OS app launcher (Linux/macOS/Windows)."""
    platform = sys.platform
    if platform.startswith('linux'):
        _install_linux_entry(install_dir, dry_run)
    elif platform == 'darwin':
        _install_macos_entry(install_dir, dry_run)
    elif platform == 'win32':
        _install_windows_entry(install_dir, dry_run)
    else:
        print(f'Warning: unsupported platform {platform!r} — skipping OS registration')


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
        description='Install natronmcp startup hook and register Natron with the OS launcher')
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

    if args.natron_install_dir:
        natron_dir = Path(args.natron_install_dir)
    else:
        natron_dir = find_natron_install()
    if natron_dir:
        install_os_entry(natron_dir, args.dry_run)
    else:
        print('Natron not found — skipping OS registration. '
              'Use --natron-install-dir to specify the install path.')


if __name__ == '__main__':
    main()
