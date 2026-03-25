"""
natron_rag.py — BM25-based search over Natron's bundled HTML documentation.

No external dependencies — stdlib only.

Build the index first:
    python scripts/fetch_natron_docs.py

Then the MCP bridge exposes two tools: search_docs and get_doc.
"""

import json
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
DOCS_DIR   = Path(os.environ.get('NATRONMCP_DOCS_DIR',   str(SCRIPT_DIR / 'natron_docs')))
INDEX_PATH = Path(os.environ.get('NATRONMCP_DOCS_INDEX', str(SCRIPT_DIR / 'natron_docs_index.json')))

_RE_WORD = re.compile(r'[a-z0-9_]+')
_STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of',
    'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 'been',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'this', 'that', 'it', 'its', 'not', 'no', 'if', 'then',
}

_BM25_K1 = 1.5
_BM25_B  = 0.75

_index: dict | None = None


def _detect_installed_version() -> str | None:
    """Best-effort: find the Natron binary and get its version string."""
    binary = shutil.which('Natron')
    if binary is None:
        # Check common dirs the same way natron_detect.py does, but inline
        # so natron_rag.py stays self-contained (no scripts/ dependency).
        platform = sys.platform
        candidates: list[Path] = []
        if platform.startswith('linux'):
            for root in (Path('/opt'), Path.home(), Path.home() / '.local'):
                try:
                    candidates += [d / 'Natron' for d in root.iterdir()
                                   if d.name.startswith('Natron')]
                except (PermissionError, FileNotFoundError):
                    pass
        elif platform == 'darwin':
            for apps in (Path('/Applications'), Path.home() / 'Applications'):
                candidates += list(apps.glob('Natron*.app/Contents/MacOS/Natron'))
        elif platform == 'win32':
            for env_var in ('LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)'):
                base = os.environ.get(env_var, '')
                if base:
                    candidates += [d / 'Natron.exe'
                                   for d in Path(base).glob('Natron*')]
        for p in candidates:
            if p.exists():
                binary = str(p)
                break

    if binary is None:
        return None

    # Try --version flag
    try:
        result = subprocess.run(
            [binary, '--version'], capture_output=True, text=True, timeout=10,
        )
        for line in (result.stdout + result.stderr).splitlines():
            m = re.search(r'(\d+\.\d+\.\d+)', line)
            if m:
                return m.group(1)
    except Exception:
        pass

    # Fallback: parse from directory name
    m = re.search(r'[Nn]atron[_-](\d+\.\d+[\.\d]*)', Path(binary).parent.name)
    if m:
        return m.group(1)

    return None


def _load_index() -> dict:
    global _index
    if _index is None:
        if not INDEX_PATH.exists():
            raise FileNotFoundError(
                f'Natron docs index not found at {INDEX_PATH}. '
                'Run: python scripts/fetch_natron_docs.py'
            )
        _index = json.loads(INDEX_PATH.read_text(encoding='utf-8'))
        _check_version(_index)
    return _index


def _check_version(idx: dict) -> None:
    indexed_version = idx.get('natron_version')
    if not indexed_version:
        return  # index predates version tracking — nothing to compare
    installed = _detect_installed_version()
    if installed and installed != indexed_version:
        print(
            f'[natron-mcp] Warning: docs index was built for Natron {indexed_version} '
            f'but Natron {installed} is installed. '
            'Re-run: uv run python scripts/fetch_natron_docs.py',
            file=sys.stderr,
        )


def _tokenize(text: str) -> list[str]:
    return [t for t in _RE_WORD.findall(text.lower()) if len(t) > 1 and t not in _STOPWORDS]


def search_docs(query: str, top_k: int = 5) -> list[dict]:
    """
    BM25 search over Natron documentation.

    Returns top_k results as [{'path': str, 'title': str, 'score': float}, ...].
    """
    idx = _load_index()
    N      = idx['N']
    avg_dl = idx['avg_dl']
    idf    = idx['idf']
    docs   = idx['docs']

    query_terms = _tokenize(query)
    if not query_terms:
        return []

    scores: dict[int, float] = {}
    for term in query_terms:
        if term not in idf:
            continue
        term_idf = idf[term]
        for i, doc in enumerate(docs):
            tf = doc['tf'].get(term, 0)
            if tf == 0:
                continue
            dl = doc['length']
            tf_norm = (tf * (_BM25_K1 + 1)) / (tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avg_dl))
            scores[i] = scores.get(i, 0.0) + term_idf * tf_norm

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    return [
        {'path': docs[i]['path'], 'title': docs[i]['title'], 'score': round(score, 4)}
        for i, score in ranked
    ]


def get_doc(path: str) -> str:
    """
    Return the text content of a documentation page by its relative path
    (as returned by search_docs). Path should use forward slashes.
    """
    # path is relative to docs dir, with .txt extension (built by fetch_natron_docs.py)
    txt_path = DOCS_DIR / Path(path).with_suffix('.txt')
    if not txt_path.exists():
        raise FileNotFoundError(f'Doc not found: {txt_path}')
    return txt_path.read_text(encoding='utf-8')
