#!/bin/bash
# Reusable installer for douyin-mcp (idempotent). Usage: ./install.sh
# Env:
#   DOUYIN_MCP_HOME  runtime dir (default: this dir)
#   SAU_DIR          where to clone social-auto-upload (default: $DOUYIN_MCP_HOME/social-auto-upload)
#   SAU_REF          upstream commit/tag/branch to check out (default: pinned commit below)
#   HTTPS_PROXY / HTTP_PROXY  optional proxy for downloads (on macOS the system proxy is used if unset)
set -x
cd "$(dirname "$0")"
HERE="$(pwd)"
DOUYIN_MCP_HOME="${DOUYIN_MCP_HOME:-$HERE}"
SAU_DIR="${SAU_DIR:-$DOUYIN_MCP_HOME/social-auto-upload}"
SAU_REPO="https://github.com/dreammis/social-auto-upload.git"
SAU_REF="${SAU_REF:-0012d2c355f88f683cc38dde2a2db209e14091bc}"   # upstream main as of 2026-09-03
export PATH="$HOME/.local/bin:$PATH"
command -v uv || curl -LsSf https://astral.sh/uv/install.sh | sh
# Optional: use the macOS system HTTPS proxy for downloads if one is configured and HTTPS_PROXY is unset
if [ -z "$HTTPS_PROXY" ] && command -v scutil >/dev/null; then
  PH=$(scutil --proxy | awk '/HTTPSProxy/{print $3}'); PP=$(scutil --proxy | awk '/HTTPSPort/{print $3}')
  [ -n "$PH" ] && [ -n "$PP" ] && export HTTPS_PROXY="http://$PH:$PP" HTTP_PROXY="http://$PH:$PP"
fi
if [ ! -d "$SAU_DIR/.git" ]; then
  git clone "$SAU_REPO" "$SAU_DIR" || exit 1
  git -C "$SAU_DIR" checkout --quiet "$SAU_REF" || exit 1
fi
cd "$SAU_DIR"
[ -d .venv ] || uv venv --python 3.12
uv pip install -e . && uv pip install -r "$HERE/requirements.txt" || exit 1
[ -f conf.py ] || cp conf.example.py conf.py
.venv/bin/patchright install chromium || PLAYWRIGHT_DOWNLOAD_HOST="https://npmmirror.com/mirrors/playwright" .venv/bin/patchright install chromium || exit 1
.venv/bin/sau douyin --help >/dev/null && echo INSTALL_DONE
