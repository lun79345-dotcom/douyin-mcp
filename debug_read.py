#!/usr/bin/env python3
"""Debug helper: open a douyin.com page with your saved sau login state and log XHR endpoints.

Usage: debug_read.py <url> [headed]
  Run with the sau venv python, e.g. "$SAU_DIR/.venv/bin/python debug_read.py '<douyin url>' headed".

Privacy: prints only whether the login-state file exists and how many cookies it holds (never names or
values), XHR paths without query strings, and response *shapes* (status_code / top-level keys / item count).
Page body text and screenshots can contain your account's nickname/avatar, so they are OFF by default:
  DEBUG_READ_BODY=1        print first 400 chars of page text
  DEBUG_READ_SCREENSHOT=1  write debug.png into $DOUYIN_MCP_HOME (git-ignored; do not share it)
"""
import asyncio, json, sys, os
from pathlib import Path
HERE = Path(__file__).resolve().parent
MCP_HOME = Path(os.path.expanduser(os.environ.get("DOUYIN_MCP_HOME", str(HERE)))).resolve()
SAU = Path(os.path.expanduser(os.environ.get("SAU_DIR", str(MCP_HOME / "social-auto-upload")))).resolve()
ACCOUNT = os.environ.get("DOUYIN_ACCOUNT", "default")
sys.path = [p for p in sys.path if Path(p or ".").resolve() != HERE]
sys.path.insert(0, str(SAU)); os.chdir(SAU)
from patchright.async_api import async_playwright
from utils.base_social_media import set_init_script
CF = SAU / "cookies" / f"douyin_{ACCOUNT}.json"
async def main(url, headed):
    if not CF.exists():
        sys.exit(f"no login state for account '{ACCOUNT}'; log in first (get_login_qrcode / sau douyin login)")
    st = json.loads(CF.read_text())
    print("login state: present, cookies:", len(st.get("cookies", [])))
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=not headed, channel="chromium",
                                     args=["--disable-blink-features=AutomationControlled"] + (["--window-position=-2400,-2400"] if headed else []))
        ctx = await b.new_context(storage_state=str(CF), locale="zh-CN", viewport={"width": 1400, "height": 900})
        ctx = await set_init_script(ctx)
        pg = await ctx.new_page()
        async def on(r):
            if r.request.resource_type in ("xhr", "fetch") and "/im/" not in r.url:
                info = ""
                try:
                    j = await r.json(); info = f"status_code={j.get('status_code')} keys={list(j)[:8]} n_data={len(j.get('data') or [])}"
                except Exception:
                    info = f"(non-json {r.status})"
                print("XHR", r.status, r.url.split('?')[0], info)
        pg.on("response", on)
        await pg.goto(url, wait_until="domcontentloaded", timeout=60000)
        await pg.wait_for_timeout(15000)
        if os.environ.get("DEBUG_READ_SCREENSHOT") == "1":
            await pg.screenshot(path=str(MCP_HOME / "debug.png"))
            print("screenshot:", MCP_HOME / "debug.png")
        print("final", pg.url.split('?')[0], "| title", await pg.title())
        if os.environ.get("DEBUG_READ_BODY") == "1":
            txt = await pg.evaluate("document.body.innerText.slice(0,400)")
            print("body:", txt.replace("\n", " | "))
        await b.close()
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1], len(sys.argv) > 2))
