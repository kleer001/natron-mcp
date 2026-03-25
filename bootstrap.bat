@echo off
setlocal enabledelayedexpansion
REM bootstrap.bat — One-command setup for natron-mcp (Windows)
REM
REM Usage (fresh install, PowerShell):
REM   powershell -c "irm https://raw.githubusercontent.com/kleer001/natron-mcp/main/bootstrap.bat -OutFile bootstrap.bat; .\bootstrap.bat"
REM
REM Usage (re-run from inside repo):
REM   bootstrap.bat

echo.
echo === natron-mcp Bootstrap ===
echo.

REM -------------------------------------------------------
REM Step 1: Check prerequisites
REM -------------------------------------------------------
echo Step 1: Checking prerequisites

where git >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('git --version') do echo [OK]   %%v
) else (
    echo [FAIL] git is not installed. Please install from https://git-scm.com/download/win
    exit /b 1
)

set "PYTHON="
for %%c in (python3 python) do (
    if not defined PYTHON (
        where %%c >nul 2>&1
        if !errorlevel! equ 0 (
            for /f "tokens=*" %%v in ('%%c -c "import sys; v=sys.version_info; print(f\"{v.major}.{v.minor}\")" 2^>nul') do set "py_ver=%%v"
            if defined py_ver (
                for /f "tokens=1,2 delims=." %%a in ("!py_ver!") do (
                    if %%a geq 3 if %%b geq 10 set "PYTHON=%%c"
                )
            )
        )
    )
)

if defined PYTHON (
    for /f "tokens=*" %%v in ('!PYTHON! --version') do echo [OK]   %%v
) else (
    echo [FAIL] Python 3.10+ is required. Install from https://www.python.org/downloads/
    exit /b 1
)

REM Natron detection (advisory)
set "NATRON_FOUND=0"
where Natron >nul 2>&1
if %errorlevel% equ 0 (
    set "NATRON_FOUND=1"
    echo [OK]   Natron found in PATH
) else (
    if exist "%APPDATA%\Natron" (
        set "NATRON_FOUND=1"
        echo [OK]   Natron config found at %APPDATA%\Natron
    ) else (
        echo [!!]   Natron not detected (setup continues — install Natron when ready^)
    )
)

REM -------------------------------------------------------
REM Step 2: Clone repo (skip if already inside it)
REM -------------------------------------------------------
echo.
echo Step 2: Repository

if exist "pyproject.toml" if exist "natron_mcp_server.py" (
    echo [OK]   Already inside natron-mcp repo — skipping clone
    goto :skip_clone
)

echo [..]   Cloning natron-mcp...
git clone https://github.com/kleer001/natron-mcp.git
cd natron-mcp
echo [OK]   Cloned into %cd%

:skip_clone
set "REPO_DIR=%cd%"

REM -------------------------------------------------------
REM Step 3: Install uv
REM -------------------------------------------------------
echo.
echo Step 3: Package manager (uv)

where uv >nul 2>&1
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('uv --version') do echo [OK]   uv already installed: %%v
) else (
    echo [..]   Installing uv...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    where uv >nul 2>&1
    if !errorlevel! equ 0 (
        for /f "tokens=*" %%v in ('uv --version') do echo [OK]   uv installed: %%v
    ) else (
        echo [FAIL] uv installation failed. Install manually: https://docs.astral.sh/uv/
        exit /b 1
    )
)

REM -------------------------------------------------------
REM Step 4: Python environment
REM -------------------------------------------------------
echo.
echo Step 4: Python environment

if not exist ".venv" (
    echo [..]   Creating virtual environment...
    uv venv
)
echo [OK]   Virtual environment: .venv\
echo [..]   Installing dependencies...
uv sync
echo [OK]   Dependencies installed

REM -------------------------------------------------------
REM Step 5: Install Natron startup hook
REM -------------------------------------------------------
echo.
echo Step 5: Natron startup hook

if %NATRON_FOUND% equ 1 (
    echo [..]   Installing startup hook into %%APPDATA%%\Natron\init.py ...
    uv run python scripts/install.py
    echo [OK]   Startup hook installed
) else (
    echo [!!]   Natron not detected — skipping startup hook
    echo        Run later: uv run python scripts/install.py
)

REM -------------------------------------------------------
REM Step 6: Build documentation index
REM -------------------------------------------------------
echo.
echo Step 6: Documentation index (offline search)

if exist "natron_docs_index.json" (
    echo [OK]   Docs index already exists — skipping
) else (
    if %NATRON_FOUND% equ 1 (
        echo [..]   Building docs index...
        uv run python scripts/fetch_natron_docs.py
        echo [OK]   Documentation index built
    ) else (
        echo [!!]   Natron not detected — skipping docs index
        echo        Run later: uv run python scripts/fetch_natron_docs.py --docs-dir "C:\path\to\Natron\Resources\docs\html"
    )
)

REM -------------------------------------------------------
REM Step 7: Configure MCP client
REM -------------------------------------------------------
echo.
echo Step 7: MCP client configuration

set "HAVE_CLAUDE_CODE=0"
set "HAVE_CLAUDE_DESKTOP=0"

where claude >nul 2>&1
if !errorlevel! equ 0 (
    set "HAVE_CLAUDE_CODE=1"
    echo [OK]   Claude Code CLI detected
)

set "DESKTOP_CONFIG=%APPDATA%\Claude\claude_desktop_config.json"
if exist "%LOCALAPPDATA%\Programs\claude-desktop" set "HAVE_CLAUDE_DESKTOP=1"
if exist "%APPDATA%\Claude" set "HAVE_CLAUDE_DESKTOP=1"
if !HAVE_CLAUDE_DESKTOP! equ 1 echo [OK]   Claude Desktop detected

set "JSON_PATH=%REPO_DIR:\=/%"

if !HAVE_CLAUDE_CODE! equ 1 if !HAVE_CLAUDE_DESKTOP! equ 1 (
    echo.
    echo Detected both Claude Code and Claude Desktop.
    echo   1^) Claude Code  (CLI^)
    echo   2^) Claude Desktop (GUI^)
    echo   3^) Both
    set /p "MCP_CHOICE=Configure which? [1/2/3]: "
    if "!MCP_CHOICE!"=="1" goto :cfg_code_only
    if "!MCP_CHOICE!"=="2" goto :cfg_desktop_only
    if "!MCP_CHOICE!"=="3" goto :cfg_both
    echo [!!]   Invalid choice — skipping MCP configuration
    goto :cfg_done
)
if !HAVE_CLAUDE_CODE! equ 1 goto :cfg_code_only
if !HAVE_CLAUDE_DESKTOP! equ 1 goto :cfg_desktop_only

echo [!!]   Neither Claude Code nor Claude Desktop detected.
echo   Install one of:
echo     Claude Code:    https://docs.anthropic.com/en/docs/claude-code
echo     Claude Desktop: https://claude.ai/download
echo.
echo   Then re-run this script, or add to %DESKTOP_CONFIG%:
echo   {"mcpServers":{"natron":{"command":"uv","args":["--directory","%JSON_PATH%","run","python","natron_mcp_server.py"]}}}
goto :cfg_done

:cfg_both
call :do_cfg_code
call :do_cfg_desktop
goto :cfg_done

:cfg_code_only
call :do_cfg_code
goto :cfg_done

:cfg_desktop_only
call :do_cfg_desktop
goto :cfg_done

:do_cfg_code
echo [..]   Configuring Claude Code...
claude mcp remove natron >nul 2>&1
claude mcp add --transport stdio --scope user natron -- uv --directory "%REPO_DIR%" run python natron_mcp_server.py
echo [OK]   Claude Code configured (verify with: claude mcp list)
goto :eof

:do_cfg_desktop
echo [..]   Configuring Claude Desktop...
!PYTHON! -c "import json,sys,os;cf=r'%DESKTOP_CONFIG%';rd=r'%REPO_DIR%';c=json.load(open(cf)) if os.path.exists(cf) else {};c.setdefault('mcpServers',{})['natron']={'command':'uv','args':['--directory',rd,'run','python','natron_mcp_server.py']};os.makedirs(os.path.dirname(cf),exist_ok=True);f=open(cf,'w');json.dump(c,f,indent=2);f.write('\n');f.close()"
echo [OK]   Claude Desktop configured: %DESKTOP_CONFIG%
goto :eof

:cfg_done

REM -------------------------------------------------------
REM Done
REM -------------------------------------------------------
echo.
echo === Setup complete! ===
echo   Repo:   %REPO_DIR%
echo   Venv:   %REPO_DIR%\.venv\
if %NATRON_FOUND% equ 0 (
    echo   After installing Natron, run:
    echo     cd %REPO_DIR% ^& uv run python scripts/install.py
)
echo.
echo   Launch Natron, then start Claude Code.
echo.
