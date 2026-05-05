# maimai-cli

Unofficial CLI helpers and an optional Codex/agent skill for user-authorized Maimai web sessions.

`maimai-cli` is designed for interactive, low-volume reading of Maimai content that the signed-in user can already view in the browser. The repository contains two pieces:

- `maimai`, a local command-line tool published on PyPI.
- `skill/`, a routing skill that teaches an agent when and how to use the CLI safely.

It does not provide login bypasses, QR login, browser-cookie extraction, CAPTCHA solving, anti-bot bypasses, or bulk scraping workflows.

## 中文简介

`maimai-cli` 是一个非官方的脉脉本机命令行工具，用来读取当前登录用户本来就能在网页端看到的内容，例如推荐流、热榜、同事圈、搜索结果、帖子详情、评论、图片和资料卡。

这个仓库同时提供：

- `maimai` CLI：发布在 PyPI 上的命令行工具。
- `skill/`：给 Codex/Agent 使用的路由技能，帮助 Agent 在用户提到脉脉、同事圈、推荐流、评论、Cookie 等场景时正确调用 CLI。

安全边界：

- 不支持扫码登录。
- 不自动读取浏览器 Cookie。
- 不绕过登录、验证码、风控或权限控制。
- 只适合低频、交互式地查看用户自己有权限访问的内容。
- 不建议把完整 Cookie 发到聊天里，推荐在本机终端通过环境变量或标准输入导入。

快速开始：

```bash
pip install maimai-cli
maimai --help
maimai import-cookie-header
maimai status
maimai feed --limit 10
maimai company-feed --limit 10
```

安装 Agent skill：

```bash
cp -R skill ~/.agents/skills/maimai-cli
```

## Safety Model

- You must provide your own valid Cookie header from a browser session you control.
- The CLI does not read browser cookie stores automatically.
- Cookies are stored locally under `~/.maimai-cli/cookies.json` with best-effort `0600` permissions.
- The CLI only uses same-origin Maimai web endpoints and user-visible pages.
- Do not use this project to access accounts, companies, feeds, posts, comments, or profiles that you are not authorized to view.
- Respect Maimai's terms, privacy expectations, rate limits, and applicable law.
- Keep request volume low. This tool is designed for interactive use, not continuous crawling.
- If a Cookie header is exposed in chat, rotate it by logging out or refreshing the browser session.

## Install

From PyPI:

```bash
pip install maimai-cli
maimai --help
```

With `uvx`:

```bash
uvx maimai-cli --help
```

From source:

```bash
git clone https://github.com/mariotong/maimai-cli.git
cd maimai-cli
uv run maimai --help
```

## Agent Skill

The repository includes a Codex/agent skill at `skill/`. Install it into your local skill root if you want agents to route Maimai-related requests to this CLI:

```bash
cp -R skill ~/.agents/skills/maimai-cli
```

The skill is intended to trigger when a user mentions Maimai, maimai, 职言, 同事圈, 推荐流, 热榜, 帖子详情, 评论, Cookie, or related troubleshooting.

Skill references:

| User intent | Reference |
| --- | --- |
| Authentication, Cookie import, safety boundaries | `skill/references/auth.md` |
| Recommended feed, hot rank, company circle, pagination | `skill/references/feeds.md` |
| Search content and contacts | `skill/references/search.md` |
| Details, comments, images, profiles, short indexes | `skill/references/detail.md` |
| Troubleshooting and common workflows | `skill/references/troubleshooting.md` |

Agent usage principles from the skill:

1. Verify `maimai --help` and `maimai status` before deeper workflows.
2. Start list reads with small limits, for example `maimai feed --limit 5`.
3. Treat `1`, `2`, and similar numeric values as short indexes only after checking recent list context.
4. Summarize output by default; use `--json`, `--yaml`, or `--raw` only when needed.
5. Never ask users to paste complete Cookie headers into chat.

## Authentication

Import a Cookie header explicitly:

```bash
maimai import-cookie-header --cookie '<paste your Cookie header here>'
```

You can also use an environment variable or stdin:

```bash
MAIMAI_COOKIE='<paste your Cookie header here>' maimai import-cookie-header
```

Check local authentication evidence:

```bash
maimai status
maimai me
maimai cookies
```

Remove saved cookies:

```bash
maimai logout
```

## Common Commands

Read a visible community feed:

```bash
maimai feed --type recommended --limit 20
maimai feed --type gossip --offset 20 --limit 20
maimai feed --page 2 --page-size 10
```

Read hot rank:

```bash
maimai hot-rank --limit 20
```

Read the current account's visible company circle feed:

```bash
maimai company-feed --limit 20
```

Read a specific company circle if you already know its `webcid`:

```bash
maimai company-feed <webcid> --limit 20
```

If automatic company-circle discovery fails with an HTTP 406/404 or an empty result, open the company circle in the browser and copy the `webcid` from the URL:

```text
https://maimai.cn/company/gossip_discuss?webcid=<webcid>
```

Then pass it explicitly:

```bash
maimai company-feed <webcid> --limit 20
```

Search visible content and contacts:

```bash
maimai search "keyword" --limit 5
maimai search "keyword" --section gossips
maimai search "keyword" --section contacts
```

After any listing command, entries are saved as short indexes. Use those indexes for details, comments, images, and profiles:

```bash
maimai refs
maimai detail 1 --kind gossip
maimai comments 1 --kind gossip --limit 20
maimai images 1 --kind gossip
maimai profile 1
```

Use structured output for scripts:

```bash
maimai feed --type gossip --limit 5 --json
maimai hot-rank --yaml
```

Use `--raw` only when you explicitly need the full parsed response:

```bash
maimai company-feed --raw
```

## Short Indexes

List commands save a local reference table at `~/.maimai-cli/refs.json`. Follow-up commands can use the latest list's 1-based indexes instead of copying raw IDs:

```bash
maimai feed --type gossip --limit 10
maimai refs
maimai detail 1 --kind gossip
maimai comments 1 --kind gossip
```

If a short index points to the wrong item, run `maimai refs` to inspect the current cache. A later list command replaces the short-index context.

## Dynamic Action IDs

Some Maimai web features use Next.js server action IDs. The CLI ships with known defaults and keeps a local runtime cache at `~/.maimai-cli/actions.json`. If an action fails, the client can scan currently visible pages for candidate action IDs, retry conservatively, and cache a working value.

This mechanism is for compatibility with normal web-page changes. It is not intended to bypass access controls or anti-abuse systems.

## Troubleshooting

Check auth first:

```bash
maimai status
maimai cookies
maimai me
```

If auth looks stale:

```bash
maimai logout
MAIMAI_COOKIE='<paste your new Cookie header here>' maimai import-cookie-header
maimai status
```

If list follow-up commands fail:

```bash
maimai refs
```

If search pagination appears unchanged, note that the current Maimai web search endpoint may ignore offset/page parameters.

If `maimai company-feed` fails during automatic company-circle discovery, pass the browser URL's `webcid` explicitly:

```bash
maimai company-feed <webcid> --limit 20
```

## Development

Run local checks:

```bash
uv run python -m py_compile maimai_cli/*.py maimai_cli/commands/*.py
uv run python -m unittest
```

Build the package:

```bash
uv build
```

Publish to PyPI:

```bash
UV_PUBLISH_TOKEN='<your PyPI API token>' uv publish
```

## Project Status

Alpha. Endpoints and page structures may change without notice. Expect breakage and treat output as best-effort.

## Disclaimer

This project is unofficial and is not affiliated with, endorsed by, or sponsored by Maimai. Use it only with accounts and data you are authorized to access.
