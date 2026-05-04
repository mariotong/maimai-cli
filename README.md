# maimai-cli

Unofficial CLI helpers for user-authorized Maimai web sessions.

This project is intended for personal, low-volume access to content that the signed-in user can already view in the browser. It does not provide login bypasses, CAPTCHA solving, anti-bot bypasses, or bulk scraping workflows.

## Safety Model

- You must provide your own valid Cookie header from a browser session you control.
- Cookies are stored locally under `~/.maimai-cli/cookies.json` with best-effort `0600` permissions.
- The CLI only uses same-origin Maimai web endpoints and user-visible pages.
- Do not use this project to access accounts, companies, feeds, posts, comments, or profiles that you are not authorized to view.
- Respect Maimai's terms, privacy expectations, rate limits, and applicable law.
- Keep request volume low. This tool is designed for interactive use, not continuous crawling.

## Install

From source:

```bash
git clone https://github.com/mariotong/maimai-cli.git
cd maimai-cli
uv run maimai --help
```

Or with pip once packaged:

```bash
pip install .
maimai --help
```

## Authentication

This CLI does not read browser cookie stores automatically and does not support QR login. Import a Cookie header explicitly:

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
```

Remove saved cookies:

```bash
maimai logout
```

## Usage

Read a visible community feed:

```bash
maimai feed --type recommended --limit 20
maimai feed --type gossip --offset 20 --limit 20
```

Read the current account's visible company circle feed:

```bash
maimai company-feed --limit 20
```

Read a specific company circle if you already know its `webcid`:

```bash
maimai company-feed <webcid> --limit 20
```

After any listing command, entries are saved as short indexes. You can use those indexes for details, comments, images, and profiles:

```bash
maimai detail 1 --kind gossip
maimai comments 1 --kind gossip --limit 20
maimai images 1 --kind gossip
```

Search visible content:

```bash
maimai search "keyword" --limit 5
```

Use JSON output for scripts:

```bash
maimai feed --type gossip --limit 5 --json
```

## Dynamic Action IDs

Some Maimai web features use Next.js server action IDs. The CLI ships with known defaults and keeps a local runtime cache at `~/.maimai-cli/actions.json`. If an action fails, the client can scan currently visible pages for candidate action IDs, retry conservatively, and cache a working value.

This mechanism is for compatibility with normal web-page changes. It is not intended to bypass access controls or anti-abuse systems.

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

## Project Status

Alpha. Endpoints and page structures may change without notice. Expect breakage and treat output as best-effort.

## Disclaimer

This project is unofficial and is not affiliated with, endorsed by, or sponsored by Maimai. Use it only with accounts and data you are authorized to access.
