#!/bin/bash
# (Re)start douyin-mcp in background. Log: $DOUYIN_MCP_HOME/server.log
# Env: DOUYIN_MCP_HOME (default: this dir), SAU_DIR (default: $DOUYIN_MCP_HOME/social-auto-upload), DOUYIN_MCP_PORT (18070)
cd "$(dirname "$0")"
HERE="$(pwd)"
export DOUYIN_MCP_HOME="${DOUYIN_MCP_HOME:-$HERE}"
export SAU_DIR="${SAU_DIR:-$DOUYIN_MCP_HOME/social-auto-upload}"
PORT="${DOUYIN_MCP_PORT:-18070}"
LOG="$DOUYIN_MCP_HOME/server.log"; PIDF="$DOUYIN_MCP_HOME/server.pid"
mkdir -p "$DOUYIN_MCP_HOME"
PIDS=$(lsof -ti tcp:$PORT -sTCP:LISTEN 2>/dev/null); [ -n "$PIDS" ] && kill $PIDS && sleep 1
nohup "$SAU_DIR/.venv/bin/python" "$HERE/server.py" >> "$LOG" 2>&1 &
echo $! > "$PIDF"
for i in $(seq 1 20); do sleep 1; lsof -ti tcp:$PORT -sTCP:LISTEN >/dev/null 2>&1 && { echo "douyin-mcp up: http://${DOUYIN_MCP_HOST:-127.0.0.1}:$PORT/mcp (pid $(cat "$PIDF"))"; exit 0; }; done
echo "douyin-mcp failed to start; see $LOG"; tail -20 "$LOG"; exit 1
