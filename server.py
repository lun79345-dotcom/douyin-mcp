#!/usr/bin/env python3
"""douyin-mcp: thin MCP server over dreammis/social-auto-upload (sau CLI) + simple read tools.

Transport: streamable HTTP at http://$DOUYIN_MCP_HOST:$DOUYIN_MCP_PORT/mcp (default 127.0.0.1:18070)
Publish tools are dry-run unless confirm=true. Read tools reuse the login-state file written by `sau douyin login`.

Environment:
  DOUYIN_MCP_HOME   runtime dir for logs (default: directory of this file)
  SAU_DIR           social-auto-upload checkout (default: $DOUYIN_MCP_HOME/social-auto-upload)
  DOUYIN_ACCOUNT, DOUYIN_MCP_HOST, DOUYIN_MCP_PORT, DOUYIN_MIN_INTERVAL, DOUYIN_READ_HEADLESS
"""
import asyncio, json, os, re, shlex, subprocess, sys, time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
MCP_HOME = Path(os.path.expanduser(os.environ.get("DOUYIN_MCP_HOME", str(HERE)))).resolve()
SAU_DIR = Path(os.path.expanduser(os.environ.get("SAU_DIR", str(MCP_HOME / "social-auto-upload")))).resolve()
SAU_BIN = SAU_DIR / ".venv" / "bin" / "sau"
COOKIE_DIR = SAU_DIR / "cookies"  # login state written by sau; never commit this directory
LOGIN_LOG = MCP_HOME / "login.log"
DEFAULT_ACCOUNT = os.environ.get("DOUYIN_ACCOUNT", "default")
HOST = os.environ.get("DOUYIN_MCP_HOST", "127.0.0.1")
PORT = int(os.environ.get("DOUYIN_MCP_PORT", "18070"))
MIN_INTERVAL = float(os.environ.get("DOUYIN_MIN_INTERVAL", "4"))  # seconds between read navigations
READ_TIMEOUT = 60
# Headless Chromium gets Douyin's captcha interstitial (验证码中间页); default to a headed window parked off-screen.
READ_HEADLESS = os.environ.get("DOUYIN_READ_HEADLESS", "0") == "1"
PUBLISH_TIMEOUT = 900

# drop our own dir from sys.path: the helper ./mcp.py next to this file would shadow the `mcp` package
sys.path = [p for p in sys.path if Path(p or ".").resolve() != HERE]
sys.path.insert(0, str(SAU_DIR))
os.chdir(SAU_DIR)  # sau's conf.py / BASE_DIR live here

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("douyin-mcp", host=HOST, port=PORT)
_read_lock = asyncio.Lock()
_last_nav = 0.0


def _ok(**kw):
    return json.dumps({"ok": True, **kw}, ensure_ascii=False, indent=1)


def _err(msg, **kw):
    return json.dumps({"ok": False, "error": msg, **kw}, ensure_ascii=False, indent=1)


def _cookie_file(account):
    return COOKIE_DIR / f"douyin_{account}.json"


def _safe_account(account):
    account = (account or DEFAULT_ACCOUNT).strip()
    if not re.fullmatch(r"[A-Za-z0-9_\-]{1,40}", account):
        raise ValueError("account must match [A-Za-z0-9_-]{1,40}")
    return account


async def _run(cmd, timeout):
    """Run a command asynchronously with a hard timeout; returns (code, output)."""
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(SAU_DIR), stdout=subprocess.PIPE,
                                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return -1, f"timeout after {timeout}s"
    text = out.decode("utf-8", "replace")
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    return proc.returncode, text[-4000:]


def _check_schedule(s):
    if not s:
        return None
    dt = datetime.strptime(s.strip(), "%Y-%m-%d %H:%M")  # sau's SCHEDULE_FORMAT
    if dt <= datetime.now():
        raise ValueError("schedule_time must be in the future")
    return dt.strftime("%Y-%m-%d %H:%M")


def _tags_str(tags):
    if isinstance(tags, str):
        tags = re.split(r"[,，\s]+", tags)
    return ",".join(t.strip().lstrip("#") for t in (tags or []) if t and t.strip().lstrip("#"))


def _existing(p, label):
    path = Path(os.path.expanduser(p)).resolve()
    if not path.is_file():
        raise ValueError(f"{label} not found: {path}")
    return str(path)

# ---------------------------------------------------------------- account tools

@mcp.tool()
async def check_login(account: str = "") -> str:
    """Check whether the Douyin creator cookie for `account` is valid (runs `sau douyin check`, ~10-60s)."""
    try:
        account = _safe_account(account)
        cf = _cookie_file(account)
        if not cf.exists():
            return _ok(logged_in=False, account=account, cookie_file=str(cf),
                       hint="No cookie yet. Call get_login_qrcode, scan with the Douyin app.")
        code, out = await _run([str(SAU_BIN), "douyin", "check", "--account", account], 240)
        valid = code == 0 and "valid" in out and "invalid" not in out
        return _ok(logged_in=valid, account=account, cookie_file=str(cf), output=out[-800:])
    except Exception as e:
        return _err(f"check_login failed: {e}")


@mcp.tool()
async def get_login_qrcode(account: str = "") -> str:
    """Open a VISIBLE Chromium window on this machine showing the Douyin creator login QR (runs
    `sau douyin login --account <account> --headed` in background). Scan it with the Douyin app, then
    call check_login. The QR PNG is also saved under social-auto-upload/cookies/. Login waits ~2-3 min."""
    try:
        account = _safe_account(account)
        log = open(LOGIN_LOG, "ab")
        proc = subprocess.Popen([str(SAU_BIN), "douyin", "login", "--account", account, "--headed"],
                                cwd=str(SAU_DIR), stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        await asyncio.sleep(12)
        qrs = sorted(COOKIE_DIR.glob(f"douyin_{account}_login_qrcode_*.png"), key=lambda p: p.stat().st_mtime)
        return _ok(started=True, pid=proc.pid, still_running=proc.poll() is None, account=account,
                   qrcode_png=str(qrs[-1]) if qrs else None, log=str(LOGIN_LOG),
                   next="Scan the QR in the browser window with the Douyin app, then call check_login.")
    except Exception as e:
        return _err(f"get_login_qrcode failed: {e}")

# ---------------------------------------------------------------- publish tools

@mcp.tool()
async def publish_video(file_path: str, title: str, desc: str = "", tags: list[str] | str = "",
                        schedule_time: str = "", thumbnail: str = "", account: str = "",
                        confirm: bool = False) -> str:
    """Publish ONE video to Douyin via `sau douyin upload-video`.
    DRY-RUN unless confirm=true (returns the exact command it would run).
    schedule_time: 'YYYY-MM-DD HH:MM' local time (optional; empty = publish immediately).
    thumbnail: optional 3:4 portrait cover image. Private/visibility and draft are NOT supported by sau for Douyin."""
    try:
        account = _safe_account(account)
        if not title.strip():
            raise ValueError("title is required")
        cmd = [str(SAU_BIN), "douyin", "upload-video", "--account", account,
               "--file", _existing(file_path, "video"), "--title", title.strip()]
        if desc: cmd += ["--desc", desc]
        t = _tags_str(tags)
        if t: cmd += ["--tags", t]
        s = _check_schedule(schedule_time)
        if s: cmd += ["--schedule", s]
        if thumbnail: cmd += ["--thumbnail", _existing(thumbnail, "thumbnail")]
        plan = dict(account=account, title=title.strip(), desc=desc, tags=t.split(",") if t else [],
                    schedule_time=s or "immediate", command=shlex.join(cmd))
        if confirm is not True:
            return _ok(dry_run=True, **plan, note="Nothing published. Re-call with confirm=true to publish.")
        if not _cookie_file(account).exists():
            return _err("not logged in; call get_login_qrcode first", **plan)
        code, out = await _run(cmd, PUBLISH_TIMEOUT)
        if code == 0:
            return _ok(published=True, **plan, output=out)
        return _err(f"sau exited {code}", **plan, output=out)
    except Exception as e:
        return _err(f"publish_video failed: {e}")


@mcp.tool()
async def publish_images(image_paths: list[str], title: str, note: str = "", tags: list[str] | str = "",
                         schedule_time: str = "", bgm: str = "", account: str = "",
                         confirm: bool = False) -> str:
    """Publish ONE image note (图文, up to 35 images, no GIF) via `sau douyin upload-note`.
    DRY-RUN unless confirm=true. schedule_time: 'YYYY-MM-DD HH:MM' (optional). bgm: optional music name."""
    try:
        account = _safe_account(account)
        if not title.strip():
            raise ValueError("title is required")
        if isinstance(image_paths, str):
            image_paths = [image_paths]
        if not image_paths or len(image_paths) > 35:
            raise ValueError("need 1-35 images")
        imgs = [_existing(p, "image") for p in image_paths]
        if any(i.lower().endswith(".gif") for i in imgs):
            raise ValueError("GIF not supported by Douyin notes")
        cmd = [str(SAU_BIN), "douyin", "upload-note", "--account", account, "--images", *imgs,
               "--title", title.strip()]
        if note: cmd += ["--note", note]
        t = _tags_str(tags)
        if t: cmd += ["--tags", t]
        if bgm: cmd += ["--bgm", bgm]
        s = _check_schedule(schedule_time)
        if s: cmd += ["--schedule", s]
        plan = dict(account=account, title=title.strip(), note=note, images=imgs,
                    tags=t.split(",") if t else [], schedule_time=s or "immediate", command=shlex.join(cmd))
        if confirm is not True:
            return _ok(dry_run=True, **plan, hint="Nothing published. Re-call with confirm=true to publish.")
        if not _cookie_file(account).exists():
            return _err("not logged in; call get_login_qrcode first", **plan)
        code, out = await _run(cmd, PUBLISH_TIMEOUT)
        if code == 0:
            return _ok(published=True, **plan, output=out)
        return _err(f"sau exited {code}", **plan, output=out)
    except Exception as e:
        return _err(f"publish_images failed: {e}")

# ---------------------------------------------------------------- read tools (browser + captured JSON)

def _aweme(a):
    if not isinstance(a, dict):
        return None
    st = a.get("statistics") or {}
    au = a.get("author") or {}
    aid = a.get("aweme_id")
    return {
        "aweme_id": aid, "desc": a.get("desc"),
        "url": f"https://www.douyin.com/video/{aid}" if aid else None,
        "create_time": datetime.fromtimestamp(a["create_time"]).strftime("%Y-%m-%d %H:%M") if a.get("create_time") else None,
        "author": {"nickname": au.get("nickname"), "sec_uid": au.get("sec_uid"), "uid": au.get("uid")},
        "stats": {k: st.get(k) for k in ("digg_count", "comment_count", "share_count", "collect_count", "play_count")},
        "duration_ms": (a.get("video") or {}).get("duration") or a.get("duration"),
        "is_images": bool(a.get("images")),
        "tags": [t.get("hashtag_name") for t in (a.get("text_extra") or []) if t.get("hashtag_name")],
    }


async def _capture(url, patterns, account, scrolls=0, wait_s=8, want=1):
    """Open `url` in headless Chromium with the sau cookie; collect JSON responses whose URL contains any pattern."""
    global _last_nav
    from patchright.async_api import async_playwright
    from utils.base_social_media import set_init_script
    account = _safe_account(account)
    cf = _cookie_file(account)
    if not cf.exists():
        raise NotLoggedIn(f"not logged in: no cookie {cf}. Call get_login_qrcode and scan with the Douyin app first.")
    got = {p: [] for p in patterns}
    async with _read_lock:
        gap = MIN_INTERVAL - (time.time() - _last_nav)
        if gap > 0:
            await asyncio.sleep(gap)
        _last_nav = time.time()
        async with async_playwright() as pw:
            args = ["--disable-blink-features=AutomationControlled"]
            if not READ_HEADLESS:
                args += ["--window-position=-2400,-2400", "--window-size=1400,900"]
            browser = await pw.chromium.launch(headless=READ_HEADLESS, channel="chromium", args=args)
            try:
                ctx = await browser.new_context(storage_state=str(cf),
                                                locale="zh-CN", viewport={"width": 1400, "height": 900})
                ctx = await set_init_script(ctx)
                page = await ctx.new_page()

                async def on_resp(r):
                    for p in patterns:
                        if p in r.url:
                            try:
                                got[p].append(await r.json())
                            except Exception:
                                pass
                page.on("response", on_resp)
                await page.goto(url, wait_until="domcontentloaded", timeout=READ_TIMEOUT * 1000)
                deadline = time.time() + wait_s
                while time.time() < deadline and sum(len(v) for v in got.values()) < want:
                    await page.wait_for_timeout(500)
                for _ in range(scrolls):
                    await page.mouse.wheel(0, 2500)
                    await page.wait_for_timeout(2500)
                final_url = page.url
                title = await page.title()
            finally:
                await browser.close()
    return got, final_url, title, cf.exists()


class NotLoggedIn(Exception):
    pass


def _login_wall(got):
    for v in got.values():
        for d in v:
            if isinstance(d, dict) and d.get("status_code") in (2483, 8):
                return f"Douyin says not logged in (status_code {d.get('status_code')}: {d.get('status_msg')}). Re-login via get_login_qrcode."
    return None


def _video_id(s):
    s = str(s).strip()
    if re.fullmatch(r"\d{15,22}", s):
        return s
    m = re.search(r"(?:video/|note/|modal_id=|aweme_id=)(\d{15,22})", s)
    if m:
        return m.group(1)
    if "v.douyin.com" in s or "iesdouyin.com" in s:
        import urllib.request
        m2 = re.search(r"https?://\S+", s)
        req = urllib.request.Request(m2.group(0) if m2 else s, headers={"User-Agent": "Mozilla/5.0 (iPhone)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return _video_id(r.geturl()) if r.geturl() != s else None
    return None


def _hint(got, title=""):
    if "验证码" in (title or ""):
        return "Douyin showed a captcha page (验证码中间页). Wait a few minutes, or run with DOUYIN_READ_HEADLESS=0 (default)."
    return _login_wall(got) or "Possible captcha/verification page or page layout change; retry later or log in again."


@mcp.tool()
async def search_videos(keyword: str, account: str = "") -> str:
    """Search Douyin videos by keyword (first page, ~10-20 results). Opens douyin.com search headless and
    reads the /aweme/v1/web/search/ JSON. Slow (~15-30s), rate limited."""
    try:
        if not keyword.strip():
            raise ValueError("keyword is required")
        pats = ["/aweme/v1/web/search/item/", "/aweme/v1/web/general/search/"]
        got, final_url, title, logged = await asyncio.wait_for(
            _capture(f"https://www.douyin.com/search/{quote(keyword.strip())}?type=video", pats, account,
                     wait_s=15), READ_TIMEOUT + 60)
        items, seen = [], set()
        for p in pats:
            for d in got[p]:
                rows = [r.get("aweme_info") for r in (d.get("data") or []) if isinstance(r, dict)]
                rows += d.get("aweme_list") or []  # /search/item/ shape
                for row in rows:
                    a = _aweme(row)
                    if a and a["aweme_id"] and a["aweme_id"] not in seen:
                        seen.add(a["aweme_id"]); items.append(a)
        if not items:
            return _err("no search results captured (captcha/login wall or page changed)",
                        final_url=final_url, page_title=title, hint=_hint(got, title))
        return _ok(keyword=keyword, count=len(items), items=items)
    except NotLoggedIn as e:
        return _err(str(e), logged_in=False)
    except asyncio.TimeoutError:
        return _err("search_videos timed out")
    except Exception as e:
        return _err(f"search_videos failed: {e}")


@mcp.tool()
async def get_video_detail(url_or_id: str, account: str = "") -> str:
    """Get one Douyin video's details (desc, author, stats, tags) by aweme_id, douyin.com/video/<id> URL,
    modal_id URL, or v.douyin.com share link."""
    try:
        vid = _video_id(url_or_id)
        if not vid:
            raise ValueError("could not extract a video id")
        pat = "/aweme/v1/web/aweme/detail/"
        got, final_url, title, logged = await asyncio.wait_for(
            _capture(f"https://www.douyin.com/video/{vid}", [pat], account, wait_s=15), READ_TIMEOUT + 60)
        for d in got[pat]:
            a = _aweme(d.get("aweme_detail"))
            if a:
                return _ok(video=a)
        return _err("video detail not captured", aweme_id=vid, final_url=final_url, page_title=title,
                    hint=_hint(got, title))
    except NotLoggedIn as e:
        return _err(str(e), logged_in=False)
    except asyncio.TimeoutError:
        return _err("get_video_detail timed out")
    except Exception as e:
        return _err(f"get_video_detail failed: {e}")


@mcp.tool()
async def get_comments(url_or_id: str, account: str = "") -> str:
    """Get the first page(s) of top-level comments for a Douyin video (id, URL, or share link)."""
    try:
        vid = _video_id(url_or_id)
        if not vid:
            raise ValueError("could not extract a video id")
        pat = "/aweme/v1/web/comment/list/"
        got, final_url, title, logged = await asyncio.wait_for(
            _capture(f"https://www.douyin.com/video/{vid}", [pat], account, scrolls=1, wait_s=15),
            READ_TIMEOUT + 60)
        out, seen, total = [], set(), None
        for d in got[pat]:
            total = d.get("total", total)
            for c in (d.get("comments") or []):
                if c.get("cid") in seen:
                    continue
                seen.add(c.get("cid"))
                u = c.get("user") or {}
                out.append({"cid": c.get("cid"), "text": c.get("text"), "digg_count": c.get("digg_count"),
                            "reply_count": c.get("reply_comment_total"), "user": u.get("nickname"),
                            "ip_label": c.get("ip_label"),
                            "create_time": datetime.fromtimestamp(c["create_time"]).strftime("%Y-%m-%d %H:%M") if c.get("create_time") else None})
        if not out and not got[pat]:
            return _err("comments not captured", aweme_id=vid, final_url=final_url, page_title=title,
                        hint=_hint(got, title))
        return _ok(aweme_id=vid, total=total, count=len(out), comments=out)
    except NotLoggedIn as e:
        return _err(str(e), logged_in=False)
    except asyncio.TimeoutError:
        return _err("get_comments timed out")
    except Exception as e:
        return _err(f"get_comments failed: {e}")


@mcp.tool()
async def get_user_posts(user_url: str, account: str = "", scrolls: int = 1) -> str:
    """Get a Douyin user's profile + recent posts. user_url: https://www.douyin.com/user/<sec_uid> (or the sec_uid).
    scrolls (0-5) loads more pages."""
    try:
        u = user_url.strip()
        m = re.search(r"/user/([A-Za-z0-9_\-]+)", u)
        sec = m.group(1) if m else (u if re.fullmatch(r"[A-Za-z0-9_\-]{20,}", u) else None)
        if not sec:
            raise ValueError("need https://www.douyin.com/user/<sec_uid> or a sec_uid")
        pats = ["/aweme/v1/web/aweme/post/", "/aweme/v1/web/user/profile/other/"]
        got, final_url, title, logged = await asyncio.wait_for(
            _capture(f"https://www.douyin.com/user/{sec}", pats, account,
                     scrolls=max(0, min(int(scrolls), 5)), wait_s=15, want=2), READ_TIMEOUT + 90)
        prof = None
        for d in got[pats[1]]:
            ui = d.get("user") or {}
            if ui:
                prof = {k: ui.get(k) for k in ("nickname", "unique_id", "signature", "follower_count",
                                               "following_count", "total_favorited", "aweme_count", "ip_location")}
        posts, seen = [], set()
        for d in got[pats[0]]:
            for a in (d.get("aweme_list") or []):
                x = _aweme(a)
                if x and x["aweme_id"] not in seen:
                    seen.add(x["aweme_id"]); posts.append(x)
        if not posts and not prof:
            return _err("user data not captured", sec_uid=sec, final_url=final_url, page_title=title,
                        hint=_hint(got, title))
        return _ok(sec_uid=sec, profile=prof, count=len(posts), posts=posts)
    except NotLoggedIn as e:
        return _err(str(e), logged_in=False)
    except asyncio.TimeoutError:
        return _err("get_user_posts timed out")
    except Exception as e:
        return _err(f"get_user_posts failed: {e}")


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
