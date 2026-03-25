#!/usr/bin/env python3
"""
install.py — Set up natronmcp for automatic loading in Natron.

This script writes ~/.Natron/init.py (or appends to it if it already exists)
so that Natron loads the MCP TCP server automatically at startup.

Usage:
    python scripts/install.py
    python scripts/install.py --natron-dir /path/to/natronmcp/src  # explicit src path
    python scripts/install.py --dry-run                             # show what would be done
"""

import argparse
import os
import sys
from pathlib import Path


INIT_PY = Path.home() / '.Natron' / 'init.py'
MARKER  = '# natron-mcp auto-start'


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
    # scripts/ is one level below the repo root; src/ is at the repo root
    repo_root = Path(__file__).parent.parent
    default_src = repo_root / 'src'

    parser = argparse.ArgumentParser(description='Install natronmcp startup hook into ~/.Natron/init.py')
    parser.add_argument('--natron-dir', default=str(default_src),
                        help=f'Path to the natronmcp src/ directory (default: {default_src})')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without writing any files')
    args = parser.parse_args()

    src_dir = Path(args.natron_dir).resolve()
    if not (src_dir / 'natronmcp').is_dir():
        print(f'Error: {src_dir}/natronmcp not found. Check --natron-dir.', file=sys.stderr)
        sys.exit(1)

    install(src_dir, args.dry_run)


if __name__ == '__main__':
    main()
