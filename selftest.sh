#!/bin/bash
# Non-destructive self test: server up, tools/list, login status, publish dry-runs, read-tool guards,
# headless browser launch. NEVER publishes (no confirm=true is ever sent).
cd "$(dirname "$0")"
export DOUYIN_MCP_HOME="${DOUYIN_MCP_HOME:-$(pwd)}"
SAU_DIR="${SAU_DIR:-$DOUYIN_MCP_HOME/social-auto-upload}"
P="$SAU_DIR/.venv/bin/python"; fail=0
echo "== tools/list"; $P mcp.py --list || { echo "FAIL: server not responding (run ./start.sh)"; exit 1; }
echo "== check_login"; $P mcp.py check_login '{}'
D=$(mktemp -d); TMP="$D/selftest.mp4"; echo x > "$TMP"
echo "== publish_video dry-run (confirm omitted)"
OUT=$($P mcp.py publish_video "{\"file_path\":\"$TMP\",\"title\":\"selftest\",\"tags\":[\"a\",\"b\"]}"); echo "$OUT"
echo "$OUT" | grep -q '"dry_run": true' || { echo "FAIL: publish_video not dry-run"; fail=1; }
echo "== publish_images dry-run"
OUT=$($P mcp.py publish_images "{\"image_paths\":[\"$TMP\"],\"title\":\"selftest\"}"); echo "$OUT"
echo "$OUT" | grep -q '"dry_run": true' || { echo "FAIL: publish_images not dry-run"; fail=1; }
rm -rf "$D"
echo "== read tool (search_videos)"; $P mcp.py search_videos '{"keyword":"test"}' | head -c 600; echo
echo "== headless chromium launch"
(cd "$SAU_DIR" && .venv/bin/python -c "
import asyncio
from patchright.async_api import async_playwright
async def m():
    async with async_playwright() as p:
        b=await p.chromium.launch(headless=True,channel='chromium'); pg=await b.new_page(); await pg.goto('about:blank'); print('chromium ok', b.version); await b.close()
asyncio.run(asyncio.wait_for(m(),90))") || { echo "FAIL: chromium launch"; fail=1; }
[ $fail = 0 ] && echo "SELFTEST PASS" || echo "SELFTEST FAIL"; exit $fail
