# Changelog

## 0.3.3 - 2026-05-05

- Keep post short indexes and comment short indexes in separate local caches.
- Add `maimai refs --scope comments` for inspecting comment references.
- Allow `--cid` to resolve comment short indexes when reading replies.
- Improve missing `--egid` / `--efid` guidance for raw IDs versus short indexes.
- Add regression tests for reference scopes and cached raw-ID context.

## 0.3.2 - 2026-05-05

- Improve automatic company-circle `webcid` discovery by collecting multiple candidates from visible community pages.
- Prefer `GossipCircle` deep links when resolving the current company circle.
- Retry company feed loading across discovered `webcid` candidates before failing.
- Document the fallback workflow for HTTP 406/404: pass `maimai company-feed <webcid>` explicitly from the browser URL.

## 0.3.1 - 2026-05-04

- Initial public alpha release.
- Supports explicit Cookie-header import, status checks, logout, feed reading, search, hot rank, company circle feed discovery, details, comments, profile cards, and image listing/downloading.
- Adds short-index references inspired by xhs-cli for interactive follow-up commands.
- Adds conservative runtime caching for Next.js server action IDs.
- Removes QR login and automatic browser-cookie extraction to keep authentication explicit.
