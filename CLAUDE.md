# natron-mcp — Claude Code Guidelines

## Architecture

Two-layer bridge pattern:

```
Claude (MCP stdio) → natron_mcp_server.py (Bridge) → TCP:54321 → src/natronmcp/server.py (Plugin) → NatronEngine
                   ↘ natron_rag.py (BM25 search — bundled docs, no Natron connection needed)
```

**Layer 1 — Plugin** (`src/natronmcp/server.py`):
- Runs *inside* Natron's embedded Python 3.10
- Loaded via `~/.Natron/init.py` → `scripts/install.py` sets this up
- Listens on TCP 127.0.0.1:54321
- All NatronEngine calls marshaled to main thread via a PySide QTimer work queue

**Layer 2 — Bridge** (`natron_mcp_server.py`):
- Runs as a standalone MCP server (stdio transport, FastMCP)
- Translates MCP tool calls to TCP JSON requests
- Also exposes RAG doc search tools (no Natron connection needed)

## Running

```bash
# 1. Install startup hook (once)
python scripts/install.py

# 2. Launch Natron (start the TCP server)
python scripts/launch.py

# 3. Run the MCP bridge (in Claude Code's MCP config or directly)
uv run natron_mcp_server.py
```

## Development

```bash
# Install deps
uv sync

# Run tests (no Natron needed)
uv run pytest

# Build docs index (requires Natron installed)
python scripts/fetch_natron_docs.py
```

## Key Paths

| What | Where |
|------|-------|
| Plugin (runs in Natron) | `src/natronmcp/server.py` |
| Bridge (MCP stdio) | `natron_mcp_server.py` |
| RAG search | `natron_rag.py` + `natron_docs_index.json` |
| Install hook | `scripts/install.py` |
| Launch helper | `scripts/launch.py` |
| Build docs index | `scripts/fetch_natron_docs.py` |
| API quirks | `BEST_PRACTICES.md` |
| Upcoming tools | `todo.md` |

## Critical NatronEngine Facts

See `BEST_PRACTICES.md` for the full list. Quick summary:
- Use `__main__.app1` to get the app, not `app` or `natron.getInstance()`
- `node.destroy()` not `app.deleteNode(node)`
- `dst.connectInput(idx, src)` — dst receives, src provides
- All NatronEngine calls require the Qt main thread (QTimer dispatch)
- Qt4 / PySide 1.2.4 only — no PySide2
