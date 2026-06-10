#!/usr/bin/env bash
# One-shot setup for the Instagram Carousel MCP server on a fresh machine.
# Usage:  ./setup.sh
# Needs:  Python 3.10+  and  the `claude` CLI on PATH.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
echo "→ Using $($PYTHON --version)"

echo "→ Creating virtualenv (.venv)"
"$PYTHON" -m venv .venv

echo "→ Installing dependencies"
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/python -m pip install --quiet -r requirements.txt

echo "→ Registering the MCP server with Claude Code (user scope)"
VENV_PY="$(pwd)/.venv/bin/python"
SERVER="$(pwd)/server.py"
claude mcp remove instagram-carousel --scope user >/dev/null 2>&1 || true
claude mcp add instagram-carousel --scope user -- "$VENV_PY" "$SERVER"

echo
echo "✓ Done. Verify with:  claude mcp list | grep carousel"
echo "  Then open a Claude Code session and ask it to create a carousel."
