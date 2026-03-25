#!/usr/bin/env bash
# bootstrap.sh — One-command setup for natron-mcp (Linux + macOS)
#
# Usage (fresh install):
#   curl -sSL https://raw.githubusercontent.com/kleer001/natron-mcp/main/bootstrap.sh | bash
#
# Usage (re-run from inside repo):
#   bash bootstrap.sh
set -euo pipefail

# --- Colors ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "${GREEN}[OK]${NC}   $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
warn() { echo -e "${YELLOW}[!!]${NC}   $1"; }
info() { echo -e "${CYAN}[..]${NC}   $1"; }

echo -e "\n${BOLD}=== natron-mcp Bootstrap ===${NC}\n"

OS="$(uname -s)"
case "$OS" in
    Linux)  os_label="Linux" ;;
    Darwin) os_label="macOS" ;;
    *)      fail "Unsupported OS: $OS"; exit 1 ;;
esac
info "Detected OS: $os_label"

# -------------------------------------------------------
# Step 1: Check prerequisites
# -------------------------------------------------------
echo -e "\n${BOLD}Step 1: Checking prerequisites${NC}"

if command -v git &>/dev/null; then
    ok "git found: $(git --version)"
else
    fail "git is not installed. Please install git first."
    exit 1
fi

PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        py_ver="$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
        if [ -n "$py_ver" ]; then
            major="${py_ver%%.*}"; minor="${py_ver##*.}"
            if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
                PYTHON="$cmd"; break
            fi
        fi
    fi
done

if [ -n "$PYTHON" ]; then
    ok "Python found: $($PYTHON --version)"
else
    fail "Python 3.10+ is required but not found."
    echo "  Install from https://www.python.org/downloads/"
    exit 1
fi

# Natron detection (advisory — non-blocking)
NATRON_BIN=""
NATRON_FOUND=false

if command -v Natron &>/dev/null; then
    NATRON_BIN="$(command -v Natron)"
    NATRON_FOUND=true
    ok "Natron found in PATH: $NATRON_BIN"
else
    case "$OS" in
        Linux)
            for d in /opt/Natron* "$HOME/Natron"* "$HOME/.local/Natron"*; do
                if [ -f "$d/Natron" ]; then NATRON_BIN="$d/Natron"; NATRON_FOUND=true; break; fi
            done
            ;;
        Darwin)
            for d in /Applications/Natron*.app/Contents/MacOS "$HOME/Applications/Natron"*.app/Contents/MacOS; do
                if [ -f "$d/Natron" ]; then NATRON_BIN="$d/Natron"; NATRON_FOUND=true; break; fi
            done
            ;;
    esac
    if [ "$NATRON_FOUND" = true ]; then
        ok "Natron found: $NATRON_BIN"
    else
        warn "Natron not detected (setup continues — install Natron when ready)"
    fi
fi

# -------------------------------------------------------
# Step 2: Clone repo (skip if already inside it)
# -------------------------------------------------------
echo -e "\n${BOLD}Step 2: Repository${NC}"

if [ -f "pyproject.toml" ] && [ -f "natron_mcp_server.py" ]; then
    ok "Already inside natron-mcp repo — skipping clone"
else
    info "Cloning natron-mcp..."
    git clone https://github.com/kleer001/natron-mcp.git
    cd natron-mcp
    ok "Cloned into $(pwd)"
fi

REPO_DIR="$(pwd)"

# -------------------------------------------------------
# Step 3: Install uv (skip if present)
# -------------------------------------------------------
echo -e "\n${BOLD}Step 3: Package manager (uv)${NC}"

if command -v uv &>/dev/null; then
    ok "uv already installed: $(uv --version)"
else
    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    if command -v uv &>/dev/null; then
        ok "uv installed: $(uv --version)"
    else
        fail "uv installation failed. Install manually: https://docs.astral.sh/uv/"
        exit 1
    fi
fi

# -------------------------------------------------------
# Step 4: Python environment
# -------------------------------------------------------
echo -e "\n${BOLD}Step 4: Python environment${NC}"

[ ! -d ".venv" ] && uv venv
ok "Virtual environment: .venv/"
info "Installing dependencies..."
uv sync
ok "Dependencies installed"

# -------------------------------------------------------
# Step 5: Install Natron startup hook
# -------------------------------------------------------
echo -e "\n${BOLD}Step 5: Natron startup hook${NC}"

if [ "$NATRON_FOUND" = true ]; then
    info "Installing startup hook into ~/.Natron/init.py ..."
    uv run python scripts/install.py
    ok "Startup hook installed"
else
    warn "Natron not detected — skipping startup hook"
    echo "  Run later: uv run python scripts/install.py"
fi

# -------------------------------------------------------
# Step 6: Build offline documentation index
# -------------------------------------------------------
echo -e "\n${BOLD}Step 6: Documentation index (offline search)${NC}"

if [ -f "natron_docs_index.json" ]; then
    ok "Docs index already exists — skipping"
elif [ "$NATRON_FOUND" = true ]; then
    NATRON_INSTALL_DIR="$(dirname "$NATRON_BIN")"
    DOCS_DIR="$NATRON_INSTALL_DIR/Resources/docs/html"
    if [ -d "$DOCS_DIR" ]; then
        info "Building docs index from $DOCS_DIR ..."
        uv run python scripts/fetch_natron_docs.py --docs-dir "$DOCS_DIR"
        ok "Documentation index built"
    else
        warn "Docs not found at $DOCS_DIR — skipping"
        echo "  Run later: uv run python scripts/fetch_natron_docs.py --docs-dir /path/to/Natron/Resources/docs/html"
    fi
else
    warn "Natron not detected — skipping docs index"
    echo "  Run later: uv run python scripts/fetch_natron_docs.py --docs-dir /path/to/Natron/Resources/docs/html"
fi

# -------------------------------------------------------
# Step 7: Configure MCP client
# -------------------------------------------------------
echo -e "\n${BOLD}Step 7: MCP client configuration${NC}"

HAVE_CLAUDE_CODE=false
HAVE_CLAUDE_DESKTOP=false

command -v claude &>/dev/null && HAVE_CLAUDE_CODE=true && ok "Claude Code CLI detected"

case "$OS" in
    Linux)  desktop_config="$HOME/.config/Claude/claude_desktop_config.json" ;;
    Darwin) desktop_config="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
esac

case "$OS" in
    Linux)  [ -d "/snap/claude-desktop" ] && HAVE_CLAUDE_DESKTOP=true ;;
    Darwin) [ -d "/Applications/Claude.app" ] && HAVE_CLAUDE_DESKTOP=true ;;
esac
[ -d "$(dirname "$desktop_config")" ] && HAVE_CLAUDE_DESKTOP=true
[ "$HAVE_CLAUDE_DESKTOP" = true ] && ok "Claude Desktop detected"

configure_claude_code() {
    info "Configuring Claude Code..."
    claude mcp remove natron --scope user 2>/dev/null || true
    claude mcp add --transport stdio --scope user natron -- \
        uv --directory "$REPO_DIR" run python natron_mcp_server.py
    ok "Claude Code configured (verify with: claude mcp list)"
}

configure_claude_desktop() {
    info "Configuring Claude Desktop..."
    "$PYTHON" - "$desktop_config" "$REPO_DIR" <<'PYEOF'
import json, sys, os
config_file, repo_dir = sys.argv[1], sys.argv[2]
config = json.load(open(config_file)) if os.path.exists(config_file) else {}
config.setdefault("mcpServers", {})["natron"] = {
    "command": "uv",
    "args": ["--directory", repo_dir, "run", "python", "natron_mcp_server.py"]
}
os.makedirs(os.path.dirname(config_file), exist_ok=True)
with open(config_file, "w") as f:
    json.dump(config, f, indent=2); f.write("\n")
PYEOF
    ok "Claude Desktop configured: $desktop_config"
}

if [ "$HAVE_CLAUDE_CODE" = true ] && [ "$HAVE_CLAUDE_DESKTOP" = true ]; then
    echo -e "\nDetected both ${BOLD}Claude Code${NC} and ${BOLD}Claude Desktop${NC}."
    echo "  1) Claude Code  (CLI)"; echo "  2) Claude Desktop (GUI)"; echo "  3) Both"
    if [ -t 0 ]; then
        read -rp "Configure which? [1/2/3]: " choice
    else
        info "Non-interactive mode — configuring both"; choice=3
    fi
    case "$choice" in
        1) configure_claude_code ;;
        2) configure_claude_desktop ;;
        3) configure_claude_code; configure_claude_desktop ;;
        *) warn "Invalid choice — skipping MCP configuration" ;;
    esac
elif [ "$HAVE_CLAUDE_CODE" = true ]; then
    configure_claude_code
elif [ "$HAVE_CLAUDE_DESKTOP" = true ]; then
    configure_claude_desktop
else
    warn "Neither Claude Code nor Claude Desktop detected."
    echo "  Install one of:"
    echo "    Claude Code:    https://docs.anthropic.com/en/docs/claude-code"
    echo "    Claude Desktop: https://claude.ai/download"
    echo ""
    echo "  Then re-run this script, or configure manually:"
    echo "    claude mcp add --transport stdio natron -- uv --directory \"$REPO_DIR\" run python natron_mcp_server.py"
fi

# -------------------------------------------------------
# Done
# -------------------------------------------------------
echo -e "\n${BOLD}${GREEN}=== Setup complete! ===${NC}"
echo -e "  Repo:   $REPO_DIR"
echo -e "  Venv:   $REPO_DIR/.venv/"
if [ "$NATRON_FOUND" = false ]; then
    echo -e "  ${YELLOW}After installing Natron, run:${NC}"
    echo -e "    cd $REPO_DIR && uv run python scripts/install.py"
fi
echo -e "\n  Launch Natron, then start Claude Code."
echo ""
