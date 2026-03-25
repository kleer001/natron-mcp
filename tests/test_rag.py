"""
test_rag.py — Unit tests for natron_rag.py

Builds a minimal in-memory index (no Natron, no filesystem docs).
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

_root = str(Path(__file__).parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import natron_rag


# ---------------------------------------------------------------------------
# Minimal index fixture
# ---------------------------------------------------------------------------

_DOCS = [
    {
        'path': 'guide/grade.html',
        'title': 'Grade Node',
        'tf': {'grade': 5, 'colour': 3, 'node': 2},
        'length': 10,
    },
    {
        'path': 'guide/merge.html',
        'title': 'Merge Node',
        'tf': {'merge': 4, 'composite': 3, 'node': 2},
        'length': 9,
    },
    {
        'path': 'devel/python.html',
        'title': 'Python API',
        'tf': {'python': 6, 'api': 3, 'script': 2},
        'length': 11,
    },
]

import math

def _build_index(docs):
    N = len(docs)
    from collections import Counter
    df: Counter = Counter()
    for doc in docs:
        for term in doc['tf']:
            df[term] += 1
    idf = {term: math.log(1 + (N - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}
    avg_dl = sum(d['length'] for d in docs) / N
    return {'N': N, 'avg_dl': avg_dl, 'idf': idf, 'docs': docs}


@pytest.fixture(autouse=True)
def reset_index():
    """Reset module-level cache between tests."""
    natron_rag._index = None
    yield
    natron_rag._index = None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_search_returns_relevant_result():
    idx = _build_index(_DOCS)
    natron_rag._index = idx
    results = natron_rag.search_docs('grade colour', top_k=2)
    assert results, 'Expected at least one result'
    assert results[0]['path'] == 'guide/grade.html'


def test_search_merge():
    idx = _build_index(_DOCS)
    natron_rag._index = idx
    results = natron_rag.search_docs('merge composite', top_k=3)
    assert results[0]['path'] == 'guide/merge.html'


def test_search_python_api():
    idx = _build_index(_DOCS)
    natron_rag._index = idx
    results = natron_rag.search_docs('python api script', top_k=1)
    assert results[0]['path'] == 'devel/python.html'


def test_search_top_k_limit():
    idx = _build_index(_DOCS)
    natron_rag._index = idx
    results = natron_rag.search_docs('node', top_k=1)
    assert len(results) == 1


def test_search_empty_query():
    idx = _build_index(_DOCS)
    natron_rag._index = idx
    results = natron_rag.search_docs('')
    assert results == []


def test_search_no_match():
    idx = _build_index(_DOCS)
    natron_rag._index = idx
    results = natron_rag.search_docs('xyzzy_nonexistent_term')
    assert results == []


def test_search_result_has_score():
    idx = _build_index(_DOCS)
    natron_rag._index = idx
    results = natron_rag.search_docs('grade', top_k=1)
    assert 'score' in results[0]
    assert results[0]['score'] > 0


def test_missing_index_raises():
    with patch.object(natron_rag, 'INDEX_PATH', Path('/nonexistent/index.json')):
        with pytest.raises(FileNotFoundError, match='index not found'):
            natron_rag.search_docs('grade')


def test_get_doc(tmp_path):
    doc_dir = tmp_path / 'natron_docs' / 'guide'
    doc_dir.mkdir(parents=True)
    (doc_dir / 'grade.txt').write_text('Grade node documentation text.')

    with patch.object(natron_rag, 'DOCS_DIR', tmp_path / 'natron_docs'):
        text = natron_rag.get_doc('guide/grade.html')
    assert 'Grade node' in text


def test_get_doc_missing(tmp_path):
    with patch.object(natron_rag, 'DOCS_DIR', tmp_path):
        with pytest.raises(FileNotFoundError):
            natron_rag.get_doc('guide/missing.html')
