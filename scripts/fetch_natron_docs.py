#!/usr/bin/env python3
"""
fetch_natron_docs.py — Build the BM25 index from Natron's bundled HTML docs.

Walks the Natron docs directory, parses HTML with stdlib html.parser,
and writes natron_docs/ (raw text files) + natron_docs_index.json (BM25 index).

Usage:
    python scripts/fetch_natron_docs.py
    python scripts/fetch_natron_docs.py --docs-dir /path/to/docs/html
    python scripts/fetch_natron_docs.py --out-dir /path/to/output

Defaults:
    --docs-dir  <natron-install>/Resources/docs/html
    --out-dir   <repo-root>  (writes natron_docs/ and natron_docs_index.json here)
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


# Default Natron install location
DEFAULT_NATRON_BASE = Path('/media/menser/fauna/META_VFX/software/natron/Natron-2.5.0-Linux-x86_64-no-installer')
DEFAULT_DOCS_DIR    = DEFAULT_NATRON_BASE / 'Resources' / 'docs' / 'html'


class _DocParser(HTMLParser):
    """Extract title and body text from an HTML file. Skips script/style blocks."""

    def __init__(self):
        super().__init__()
        self.title = ''
        self.text_parts: list[str] = []
        self._in_skip = False
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'head') and tag != 'title':
            self._in_skip = True
        if tag == 'title':
            self._in_title = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'head'):
            self._in_skip = False
        if tag == 'title':
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._in_skip:
            stripped = data.strip()
            if stripped:
                self.text_parts.append(stripped)

    def get_text(self) -> str:
        return ' '.join(self.text_parts)


def _parse_html(path: Path) -> tuple[str, str]:
    """Return (title, body_text) for a single HTML file."""
    parser = _DocParser()
    try:
        parser.feed(path.read_text(encoding='utf-8', errors='replace'))
    except Exception:
        pass
    return parser.title.strip(), parser.get_text()


_RE_WORD = re.compile(r'[a-z0-9_]+')
_STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of',
    'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 'been',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'this', 'that', 'it', 'its', 'not', 'no', 'if', 'then',
}


def _tokenize(text: str) -> list[str]:
    return [t for t in _RE_WORD.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS]


def build_index(docs_dir: Path, out_dir: Path):
    html_files = list(docs_dir.rglob('*.html'))
    if not html_files:
        print(f'No HTML files found under {docs_dir}', file=sys.stderr)
        sys.exit(1)

    print(f'Found {len(html_files)} HTML files in {docs_dir}')

    raw_dir = out_dir / 'natron_docs'
    raw_dir.mkdir(exist_ok=True)

    docs = []
    for path in html_files:
        rel = path.relative_to(docs_dir)
        title, body = _parse_html(path)
        text = f'{title}\n{body}'
        tokens = _tokenize(text)
        if not tokens:
            continue

        # Write raw text file
        out_path = raw_dir / rel.with_suffix('.txt')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding='utf-8')

        docs.append({
            'path':   str(rel),
            'title':  title,
            'tf':     dict(Counter(tokens)),
            'length': len(tokens),
        })

    # Compute IDF
    N = len(docs)
    df: Counter = Counter()
    for doc in docs:
        for term in doc['tf']:
            df[term] += 1

    idf = {term: (N - freq + 0.5) / (freq + 0.5) for term, freq in df.items()}
    # log IDF
    import math
    idf = {term: math.log(1 + v) for term, v in idf.items()}

    avg_dl = sum(d['length'] for d in docs) / N if N else 1

    index = {
        'N':      N,
        'avg_dl': avg_dl,
        'idf':    idf,
        'docs':   docs,
    }

    index_path = out_dir / 'natron_docs_index.json'
    index_path.write_text(json.dumps(index, separators=(',', ':')), encoding='utf-8')
    print(f'Wrote {N} docs to {raw_dir}/')
    print(f'Wrote index to {index_path}')


def main():
    repo_root = Path(__file__).parent.parent

    parser = argparse.ArgumentParser(description='Build Natron docs BM25 index')
    parser.add_argument('--docs-dir', default=str(DEFAULT_DOCS_DIR),
                        help=f'Natron HTML docs directory (default: {DEFAULT_DOCS_DIR})')
    parser.add_argument('--out-dir', default=str(repo_root),
                        help=f'Output directory for natron_docs/ and index (default: {repo_root})')
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir)
    out_dir  = Path(args.out_dir)

    if not docs_dir.is_dir():
        print(f'Error: docs directory not found: {docs_dir}', file=sys.stderr)
        print('Use --docs-dir to point to the Natron HTML docs.', file=sys.stderr)
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    build_index(docs_dir, out_dir)


if __name__ == '__main__':
    main()
