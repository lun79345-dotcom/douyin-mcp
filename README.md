# douyin-mcp

> 本地运行的抖音（Douyin）MCP 服务：扫码登录、发布视频 / 图文，以及简单的读取（搜索、视频详情、评论、用户作品）。
> A local MCP server for Douyin: QR login, publish (video / image note) and simple reads
> (search, video detail, comments, user posts).

基于 / Built on [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload)
（`sau` CLI + patchright Chromium，MIT License）。本仓库**不包含** social-auto-upload 源码，`install.sh` 会从上游克隆并固定到指定 commit。
This repo does **not** vendor social-auto-upload; `install.sh` clones it from upstream and pins a commit.

---

## ⚠️ 风险提示 / Risk notice

- **风控 / 封号风险**：本工具通过浏览器自动化操作你的抖音账号。自动化发布与读取可能触发抖音风控（验证码、限流、功能限制），严重时可能导致**账号被限制或封禁**。请低频、适度使用。
- **平台条款**：使用前请自行阅读并遵守《抖音用户服务协议》及相关平台规则、当地法律法规。自动化行为可能违反平台条款，责任由使用者自负。
- **仅使用你自己的账号**，风险自担。不要用于批量营销、刷量、爬取他人隐私或任何违法用途。
- **登录状态即账号凭证**：`social-auto-upload/cookies/` 下的文件等同于你的账号登录凭证，切勿上传、分享或提交到 Git（`.gitignore` 已默认排除）。
- **无担保**：本软件按“原样”提供，不提供任何形式的担保；作者不对任何账号损失、数据丢失或其他后果负责（见 [LICENSE](LICENSE)）。
- 本项目与抖音 / 字节跳动无任何关联。

**English:** This tool automates *your own* Douyin account through a browser. Automation may trigger Douyin's risk
controls (captchas, rate limits, feature restrictions) and **may get your account restricted or banned**. You are
responsible for complying with Douyin's Terms of Service and applicable law. Use your own account, at your own risk.
The login-state files under `social-auto-upload/cookies/` are equivalent to your password — never share or commit
them. Provided "AS IS", without warranty of any kind. Not affiliated with Douyin / ByteDance.

---

## 安装 / Install

依赖 / Requirements: macOS or Linux, `git`, `curl`, `lsof`; `uv` and Python 3.12 are installed automatically.

```bash
git clone <this repo> douyin-mcp && cd douyin-mcp
./install.sh      # uv, Python 3.12 venv, sau (editable, pinned commit), pinned deps, patchright chromium
```

Pins: `requirements.txt` (mcp, playwright) + sau's own `pyproject.toml` (patchright). Upstream commit is set via
`SAU_REF` in `install.sh`.

## 配置（环境变量）/ Configuration (env vars)

| 变量 / var | 默认 / default | 说明 / notes |
|---|---|---|
| `DOUYIN_MCP_HOME` | 仓库目录 / repo dir | 运行目录（日志、pid）/ runtime dir for logs & pid |
| `SAU_DIR` | `$DOUYIN_MCP_HOME/social-auto-upload` | social-auto-upload 位置 / checkout location |
| `SAU_REF` | pinned commit | install.sh 检出的上游版本 / upstream ref to check out |
| `HTTPS_PROXY` / `HTTP_PROXY` | 未设置 / unset | 可选下载代理，例如 `http://127.0.0.1:<port>`；macOS 下未设置时会尝试系统代理 / optional proxy for downloads |
| `DOUYIN_MCP_HOST` | `127.0.0.1` | 监听地址（建议保持本机）/ bind host (keep it local) |
| `DOUYIN_MCP_PORT` | `18070` | 端口 / port |
| `DOUYIN_MCP_URL` | `http://localhost:$DOUYIN_MCP_PORT/mcp` | `mcp.py` 客户端使用 / used by the `mcp.py` client |
| `DOUYIN_ACCOUNT` | `default` | 默认账号名（本地标签，非抖音号）/ local account label |
| `DOUYIN_MIN_INTERVAL` | `4` | 读取请求最小间隔（秒）/ min seconds between read navigations |
| `DOUYIN_READ_HEADLESS` | `0` | `1` = 纯无头（更容易遇到验证码）/ force headless (more captchas) |

## 运行 / Run / test

```bash
./start.sh                 # (re)start in background → http://127.0.0.1:18070/mcp, log: $DOUYIN_MCP_HOME/server.log
./selftest.sh              # server up, tools/list, login status, publish dry-runs, chromium launch (never publishes)
python3 mcp.py --list
python3 mcp.py <tool> '<json args>'
```

Streamable HTTP MCP endpoint: `http://127.0.0.1:18070/mcp` (FastMCP from `mcp` 1.x). Point your MCP client at it.

## 登录 / Login (once per account)

调用 `get_login_qrcode` 工具，或在终端 / Call `get_login_qrcode`, or in a terminal:

```bash
cd "${SAU_DIR:-./social-auto-upload}" && .venv/bin/sau douyin login --account default --headed
```

会打开 creator.douyin.com 登录页，用抖音 App 扫码。登录状态保存在 `$SAU_DIR/cookies/`（已被 git 忽略），用 `check_login` 检查。
如果发布时触发短信验证，把验证码写入 `$SAU_DIR/verify_code.txt`（已被 git 忽略）。
A Chromium window opens with a QR code; scan it with the Douyin app. Login state is stored under `$SAU_DIR/cookies/`
(git-ignored). If an upload triggers SMS verification, write the code into `$SAU_DIR/verify_code.txt`.

## 工具 / Tools

| tool | args | notes |
|---|---|---|
| check_login | account? | runs `sau douyin check` |
| get_login_qrcode | account? | launches visible login window (background) |
| publish_video | file_path, title, desc?, tags?, schedule_time?, thumbnail?, account?, **confirm** | dry-run unless `confirm=true` |
| publish_images | image_paths[], title, note?, tags?, schedule_time?, bgm?, account?, **confirm** | 1-35 images, no GIF; dry-run unless `confirm=true` |
| search_videos | keyword, account? | needs login |
| get_video_detail | url_or_id, account? | id, douyin.com/video/ID, modal_id=, v.douyin.com link |
| get_comments | url_or_id, account? | first page of top-level comments (~5-20) |
| get_user_posts | user_url, account?, scrolls? (0-5) | profile + recent posts |

`schedule_time`: `YYYY-MM-DD HH:MM` (local time, must be in the future). Private/visibility and drafts are not
supported by sau for Douyin. All tools return JSON text: `{"ok": true, ...}` or `{"ok": false, "error": "..."}`.

读取类工具会用你的登录状态打开真实的 douyin.com 页面，并捕获页面自身的 XHR JSON（不重新实现请求签名）。
纯无头浏览器容易遇到“验证码中间页”，因此默认使用移到屏幕外的有头窗口。遇到验证码或页面改版时返回 `ok:false` 和提示。**请低频使用以降低风控风险。**
Read tools open the real douyin.com page with your login state and capture the page's own XHR JSON
(`/aweme/v1/web/general/search/`, `/search/item/`, `/aweme/detail/`, `/comment/list/`, `/aweme/post/`,
`/user/profile/other/`); no request signing is reimplemented. Reads are serialized, ≥4 s apart.

## 调试 / Debug

```bash
"${SAU_DIR:-./social-auto-upload}/.venv/bin/python" debug_read.py '<douyin url>' headed
```

只打印 XHR 路径与响应结构，不打印 cookie 名称或值；页面文字与截图默认关闭（`DEBUG_READ_BODY=1`、`DEBUG_READ_SCREENSHOT=1` 开启，截图可能含你的头像昵称，请勿分享）。
Prints XHR paths and response shapes only — never cookie names or values. Page text / screenshot are opt-in.

## 致谢与许可 / Credits & License

- [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload) — MIT License, © dreammis. All
  upload/login automation comes from it.
- This project: MIT License, © 2026 Nickstudio. See [LICENSE](LICENSE).
