![natron-mcp](logos/banner_v2_1_gradient_sweep.png)

MCP (Model Context Protocol) bridge connecting [Natron](https://natrongithub.github.io/)
compositor to Claude AI. Control Natron's node graph, read and set parameters,
and query Natron's documentation — all from Claude Code.

## What it does

- **12 MCP tools**: node graph manipulation (create, connect, read/write parameters, execute Python) plus offline doc search
- **Offline doc search** — BM25 over Natron's bundled HTML docs, zero network calls
- Works with Natron 2.5.x (Qt4 / PySide 1.2.4)

## Architecture

```
Claude (MCP stdio) → natron_mcp_server.py → TCP:54321 → src/natronmcp/server.py → NatronEngine
                   ↘ natron_rag.py  (BM25 doc search, no Natron connection needed)
```

Two layers:
1. **Plugin** (`src/natronmcp/`) — runs *inside* Natron's embedded Python. Loaded via `~/.Natron/init.py`. Uses a PySide `QTimer` to dispatch all NatronEngine calls on the main thread.
2. **Bridge** (`natron_mcp_server.py`) — standalone MCP server (stdio). Translates tool calls to TCP JSON.

## Get Started

**Prerequisites:** [Natron 2.5.x](https://natrongithub.github.io/), Python 3.10+, [uv](https://docs.astral.sh/uv/), Claude Code or Claude Desktop

**Linux / macOS**
```bash
curl -sSL https://raw.githubusercontent.com/kleer001/natron-mcp/main/bootstrap.sh | bash
```

**Windows** (PowerShell)
```powershell
powershell -c "irm https://raw.githubusercontent.com/kleer001/natron-mcp/main/bootstrap.bat -OutFile bootstrap.bat; .\bootstrap.bat"
```

The bootstrap script clones the repo, installs dependencies via `uv`, installs the Natron startup hook, builds the offline documentation index, and configures your MCP client — all in one shot.

<details>
<summary>Manual setup (step by step)</summary>

### 1. Clone and install

```bash
git clone https://github.com/kleer001/natron-mcp
cd natron-mcp
uv sync
```

### 2. Install the Natron startup hook

```bash
uv run python scripts/install.py
```

This appends to `~/.Natron/init.py` so Natron auto-starts the TCP server on port 54321.

### 3. Build the documentation index (optional but recommended)

```bash
uv run python scripts/fetch_natron_docs.py
```

Pass `--docs-dir /path/to/Natron/Resources/docs/html` if Natron isn't in a standard location.

### 4. Configure Claude Code

```bash
claude mcp add --transport stdio --scope user natron -- uv --directory /path/to/natron-mcp run python natron_mcp_server.py
```

Or add to `claude_desktop_config.json` for Claude Desktop:

```json
{
  "mcpServers": {
    "natron": {
      "command": "uv",
      "args": ["--directory", "/path/to/natron-mcp", "run", "python", "natron_mcp_server.py"]
    }
  }
}
```

### 5. Launch Natron and start compositing

```bash
uv run python scripts/launch.py
```

</details>

## Available tools

| Tool | Description |
|------|-------------|
| `ping` | Check connectivity to Natron |
| `get_scene_info` | Project name, frame rate, frame range, node count |
| `list_nodes` | All nodes in the current project |
| `create_node` | Create a node by plugin ID |
| `get_node_info` | Node inputs and parameter names |
| `get_parameter` | Read a parameter value |
| `set_parameter` | Write a parameter value |
| `connect_nodes` | Wire src output → dst input |
| `delete_node` | Remove a node |
| `execute_python` | Run Python in Natron's Script Editor namespace |
| `search_docs` | BM25 search over Natron's offline documentation |
| `get_doc` | Return the full text of a documentation page |

## Requirements

- Natron 2.5.x (Linux/macOS/Windows)
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) or pip
- `mcp[cli]>=1.0.0`

## License

MIT
