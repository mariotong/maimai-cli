from __future__ import annotations

import json
from typing import Any

import click

from .. import refs
from ..errors import (
    INVALID_ARGUMENT,
    NOT_FOUND,
    MaimaiCliError,
)
from ..output import (
    emit_ok,
    make_pagination_hints,
    structured_output_options,
    summarize_comments,
    summarize_company_circle,
    summarize_feed_item,
    summarize_me,
    summarize_profile,
    summarize_search,
)
from .common import emit_exception, run_with_client


# ─── Reference helpers ──────────────────────────────────────────────────────


def _ref_from_feed_summary(item: dict) -> dict[str, Any] | None:
    kind = item.get("kind")
    item_id = item.get("id")
    if not kind or not item_id:
        return None
    entry: dict[str, Any] = {"kind": kind, "id": str(item_id)}
    for key in ("efid", "egid"):
        if item.get(key):
            entry[key] = item[key]
    author = item.get("author") or {}
    if isinstance(author, dict):
        if author.get("trackable_token"):
            entry["trackable_token"] = author["trackable_token"]
        if author.get("mmid"):
            entry["mmid"] = str(author["mmid"])
    if item.get("title"):
        entry["label"] = item["title"]
    elif item.get("text"):
        entry["label"] = item["text"]
    return entry


def _ref_from_comment(comment: dict) -> dict[str, Any] | None:
    cid = comment.get("id")
    if not cid:
        return None
    entry: dict[str, Any] = {"kind": "comment", "id": str(cid)}
    author = comment.get("author") or {}
    if isinstance(author, dict):
        if author.get("trackable_token"):
            entry["trackable_token"] = author["trackable_token"]
        if author.get("mmid"):
            entry["mmid"] = str(author["mmid"])
    if comment.get("text"):
        entry["label"] = comment["text"]
    return entry


def _ref_from_contact(contact: dict) -> dict[str, Any] | None:
    mmid = contact.get("mmid")
    if not mmid:
        return None
    entry: dict[str, Any] = {"kind": "contact", "id": str(mmid), "mmid": str(mmid)}
    if contact.get("trackable_token"):
        entry["trackable_token"] = contact["trackable_token"]
    label_parts = [contact.get(k) for k in ("name", "company", "position") if contact.get(k)]
    if label_parts:
        entry["label"] = " · ".join(label_parts)
    return entry


def _resolve_feed_ref(
    item_id: str,
    *,
    kind_hint: str,
    efid: str = "",
    egid: str = "",
) -> tuple[str, str, str]:
    """Resolve ``item_id`` (raw id OR short index) into (id, efid, egid)."""
    ref = refs.resolve_reference(item_id, expect_kind=kind_hint)
    if not ref and item_id.isdigit():
        raise MaimaiCliError(
            NOT_FOUND,
            f"Short index {item_id} not found. Run a listing command first "
            "(feed / search / company-feed / hot-rank).",
        )
    resolved_id = str(ref.get("id") or item_id)
    resolved_kind = ref.get("kind") or kind_hint
    if kind_hint and ref.get("kind") and ref["kind"] != kind_hint:
        # The user overrode --kind; fall through with the original id.
        resolved_kind = kind_hint
    efid = efid or ref.get("efid", "") if resolved_kind == "feed" else efid
    egid = egid or ref.get("egid", "") if resolved_kind == "gossip" else egid
    return resolved_id, efid, egid


def _missing_context_message(kind: str, field: str, command_name: str) -> str:
    listing = "maimai feed / maimai hot-rank / maimai company-feed / maimai search"
    raw_hint = (
        f"If you are using a raw {kind} id, pass its `{field}`. "
        f"If you are using a short index, rerun the list command that produced the post, "
        f"then confirm it with `maimai refs`."
    )
    return (
        f"{field} is required for {kind} {command_name}. {raw_hint} "
        f"List commands that can create short-index context: {listing}."
    )


# ─── Commands ──────────────────────────────────────────────────────────────


@click.command()
@click.option("--raw", is_flag=True, help="Print the full response. This may include personal data.")
@structured_output_options
def me(raw: bool, as_json: bool, as_yaml: bool) -> None:
    """Fetch current community user info using saved cookies."""
    def action(client):
        return client.community_user_info()

    def on_success(data):
        emit_ok(data if raw else summarize_me(data), as_json=as_json, as_yaml=as_yaml)

    run_with_client(action, as_json=as_json, as_yaml=as_yaml, on_success=on_success)


def _page_offset_limit(page: int, page_size: int, offset: int, limit: int) -> tuple[int, int]:
    if page:
        if page < 1:
            raise click.BadParameter("--page must be >= 1")
        if page_size < 1:
            raise click.BadParameter("--page-size must be >= 1")
        return (page - 1) * page_size, page_size
    if limit < 1:
        raise click.BadParameter("--limit must be >= 1")
    if offset < 0:
        raise click.BadParameter("--offset must be >= 0")
    return offset, limit


@click.command()
@click.argument("query")
@click.option("--limit", default=5, show_default=True, help="Max items per section.")
@click.option("--offset", default=0, show_default=True, help="Requested search offset. The current web API may ignore this.")
@click.option("--page", default=0, show_default=True, help="1-based page number. Overrides --offset when set.")
@click.option("--page-size", default=5, show_default=True, help="Page size used with --page.")
@click.option("--section", type=click.Choice(["all", "feeds", "gossips", "contacts"]), default="all", show_default=True)
@click.option("--raw", is_flag=True, help="Print the full response. This may include personal data.")
@structured_output_options
def search(
    query: str,
    limit: int,
    offset: int,
    page: int,
    page_size: int,
    section: str,
    raw: bool,
    as_json: bool,
    as_yaml: bool,
) -> None:
    """Search visible community content and contacts."""
    offset, limit = _page_offset_limit(page, page_size, offset, limit)

    def action(client):
        return client.search(query, limit=limit, offset=offset)

    def on_success(data):
        summarized = summarize_search(data, limit)
        if section != "all":
            summarized = {section: summarized.get(section)}

        entries: list[dict] = []
        for item in (summarized.get("feeds") or []):
            ref = _ref_from_feed_summary(item)
            if ref:
                entries.append(ref)
        for item in (summarized.get("gossips") or []):
            ref = _ref_from_feed_summary(item)
            if ref:
                entries.append(ref)
        for contact in (summarized.get("contacts") or []):
            ref = _ref_from_contact(contact)
            if ref:
                entries.append(ref)
        refs.save_index(entries, source_command="search")

        emit_ok(
            data if raw else summarized,
            query=query,
            offset=offset,
            limit=limit,
            page=page or None,
            page_size=page_size if page else None,
            section=section,
            pagination_supported=False,
            pagination_note=(
                "Maimai web search currently ignores offset/page parameters; "
                "section filtering is supported client-side."
            ),
            short_index_count=len(entries),
            as_json=as_json,
            as_yaml=as_yaml,
        )

    run_with_client(action, as_json=as_json, as_yaml=as_yaml, on_success=on_success)


@click.command()
@click.option("--type", "feed_type", default="recommended", show_default=True)
@click.option("--limit", default=10, show_default=True)
@click.option("--offset", default=0, show_default=True, help="Skip this many items before returning results.")
@click.option("--page", default=0, show_default=True, help="1-based page number. Overrides --offset when set.")
@click.option("--page-size", default=10, show_default=True, help="Page size used with --page.")
@click.option("--raw", is_flag=True, help="Print the full parsed list.")
@structured_output_options
def feed(
    feed_type: str,
    limit: int,
    offset: int,
    page: int,
    page_size: int,
    raw: bool,
    as_json: bool,
    as_yaml: bool,
) -> None:
    """Read a visible community feed."""
    offset, limit = _page_offset_limit(page, page_size, offset, limit)

    def action(client):
        return client.feed(feed_type, limit=limit, offset=offset)

    def on_success(data):
        items = data["list"]
        summarized = [summarize_feed_item(item) for item in items]
        entries = [e for e in (_ref_from_feed_summary(it) for it in summarized) if e]
        refs.save_index(entries, source_command=f"feed --type {feed_type}")

        hints = make_pagination_hints(
            command="feed",
            args=[f"--type {feed_type}"],
            offset=offset,
            limit=limit,
            loaded=len(items),
            has_more=bool(data["has_more"]),
        )

        emit_ok(
            items if raw else summarized,
            type=data["list_type"],
            offset=offset,
            limit=limit,
            page=page or None,
            page_size=page_size if page else None,
            loaded_total=data["loaded_total"],
            loaded=len(items),
            short_index_count=len(entries),
            **hints,
            as_json=as_json,
            as_yaml=as_yaml,
        )

    run_with_client(action, as_json=as_json, as_yaml=as_yaml, on_success=on_success)


@click.command("hot-rank")
@click.option("--limit", default=20, show_default=True)
@click.option("--raw", is_flag=True, help="Print the full parsed list.")
@structured_output_options
def hot_rank(limit: int, raw: bool, as_json: bool, as_yaml: bool) -> None:
    """Read the visible community hot-rank page."""
    def action(client):
        return client.hot_rank()

    def on_success(data):
        items = data["list"][:limit]
        summarized = [summarize_feed_item(item) for item in items]
        entries = [e for e in (_ref_from_feed_summary(it) for it in summarized) if e]
        refs.save_index(entries, source_command="hot-rank")
        emit_ok(
            items if raw else summarized,
            type="hot-rank",
            has_more=bool(data["has_more"]),
            short_index_count=len(entries),
            as_json=as_json,
            as_yaml=as_yaml,
        )

    run_with_client(action, as_json=as_json, as_yaml=as_yaml, on_success=on_success)


@click.command("company-feed")
@click.argument("webcid", required=False)
@click.option("--limit", default=10, show_default=True)
@click.option("--offset", default=0, show_default=True, help="Skip this many items before returning results.")
@click.option("--page", default=0, show_default=True, help="1-based page number. Overrides --offset when set.")
@click.option("--page-size", default=10, show_default=True, help="Page size used with --page.")
@click.option("--raw", is_flag=True, help="Print the full parsed list.")
@structured_output_options
def company_feed(
    webcid: str,
    limit: int,
    offset: int,
    page: int,
    page_size: int,
    raw: bool,
    as_json: bool,
    as_yaml: bool,
) -> None:
    """Read the current or specified company gossip-discuss circle."""
    offset, limit = _page_offset_limit(page, page_size, offset, limit)

    def action(client):
        return client.company_feed(webcid or "", limit=limit, offset=offset)

    def on_success(data):
        resolved_webcid = data.get("webcid") or webcid
        items = data["list"]
        summarized = [summarize_feed_item(item) for item in items]
        entries = [e for e in (_ref_from_feed_summary(it) for it in summarized) if e]
        for entry in entries:
            entry.setdefault("webcid", resolved_webcid)
        refs.save_index(entries, source_command=f"company-feed {resolved_webcid}")

        hints = make_pagination_hints(
            command="company-feed",
            args=[resolved_webcid],
            offset=offset,
            limit=limit,
            loaded=len(items),
            has_more=bool(data["has_more"]),
        )

        payload = {
            "type": "company-feed",
            "webcid": resolved_webcid,
            "offset": offset,
            "limit": limit,
            "page": page or None,
            "page_size": page_size if page else None,
            "circle": summarize_company_circle(data["circle"]),
            "count": data["count"],
            "remain": data["remain"],
            "loaded_total": data["loaded_total"],
            "fetched_until": data.get("fetched_until"),
            "loaded": len(items),
            "short_index_count": len(entries),
        }
        if data.get("pagination_error"):
            payload["pagination_error"] = data["pagination_error"]
        payload.update(hints)
        emit_ok(
            items if raw else summarized,
            **payload,
            as_json=as_json,
            as_yaml=as_yaml,
        )

    run_with_client(action, as_json=as_json, as_yaml=as_yaml, on_success=on_success)


@click.command()
@click.argument("item_id")
@click.option("--kind", type=click.Choice(["feed", "gossip"]), default="feed", show_default=True)
@click.option("--efid", default="", help="Required for feed detail unless resolved via short index.")
@click.option("--egid", default="", help="Required for gossip detail unless resolved via short index.")
@click.option("--raw", is_flag=True, help="Print the full parsed detail.")
@structured_output_options
def detail(
    item_id: str,
    kind: str,
    efid: str,
    egid: str,
    raw: bool,
    as_json: bool,
    as_yaml: bool,
) -> None:
    """Read a feed or gossip detail page. ``item_id`` can be a 1-based short index."""
    try:
        resolved_id, efid, egid = _resolve_feed_ref(item_id, kind_hint=kind, efid=efid, egid=egid)
    except MaimaiCliError as exc:
        emit_exception(exc, as_json=as_json, as_yaml=as_yaml)
        raise SystemExit(1) from exc

    if kind == "feed" and not efid:
        emit_exception(
            MaimaiCliError(INVALID_ARGUMENT, _missing_context_message("feed", "--efid", "detail")),
            as_json=as_json, as_yaml=as_yaml,
        )
        raise SystemExit(1)
    if kind == "gossip" and not egid:
        emit_exception(
            MaimaiCliError(INVALID_ARGUMENT, _missing_context_message("gossip", "--egid", "detail")),
            as_json=as_json, as_yaml=as_yaml,
        )
        raise SystemExit(1)

    def action(client):
        return client.feed_detail(resolved_id, efid) if kind == "feed" else client.gossip_detail(resolved_id, egid)

    def on_success(data):
        emit_ok(
            data if raw else summarize_feed_item(data),
            kind=kind,
            id=resolved_id,
            resolved_from_short_index=item_id.isdigit() and item_id != resolved_id,
            as_json=as_json,
            as_yaml=as_yaml,
        )

    run_with_client(action, as_json=as_json, as_yaml=as_yaml, on_success=on_success)


@click.command()
@click.argument("item_id")
@click.option("--kind", type=click.Choice(["feed", "gossip"]), default="feed", show_default=True)
@click.option("--efid", default="", help="Used to build feed referer.")
@click.option("--egid", default="", help="Required for gossip comments unless resolved via short index.")
@click.option("--cid", default="", help="Read replies for this comment id.")
@click.option("--page", default=0, show_default=True)
@click.option("--limit", default=10, show_default=True)
@click.option("--raw", is_flag=True, help="Print the full response. This may include personal data.")
@structured_output_options
def comments(
    item_id: str,
    kind: str,
    efid: str,
    egid: str,
    cid: str,
    page: int,
    limit: int,
    raw: bool,
    as_json: bool,
    as_yaml: bool,
) -> None:
    """Read comments for a feed/gossip item. ``item_id`` can be a 1-based short index."""
    try:
        resolved_id, efid, egid = _resolve_feed_ref(item_id, kind_hint=kind, efid=efid, egid=egid)
    except MaimaiCliError as exc:
        emit_exception(exc, as_json=as_json, as_yaml=as_yaml)
        raise SystemExit(1) from exc
    resolved_cid = ""
    if cid:
        comment_ref = refs.resolve_reference(cid, expect_kind="comment", scope="comments")
        resolved_cid = str(comment_ref.get("id") or cid)

    def action(client):
        return client.comments(kind=kind, item_id=resolved_id, page=page, efid=efid, egid=egid, cid=resolved_cid)

    def on_success(data):
        summarized = summarize_comments(data, limit)
        entries = [
            e for e in (_ref_from_comment(c) for c in summarized.get("items", [])) if e
        ]
        refs.save_index(entries, source_command=f"comments {resolved_id} --kind {kind}", scope="comments")

        hints: dict[str, Any] = {"has_more": bool(summarized.get("has_more"))}
        if summarized.get("has_more"):
            next_page = (page or 0) + 1
            hints["next_page"] = next_page
            extra_parts: list[str] = []
            if kind == "feed" and efid:
                extra_parts.append(f"--efid {efid}")
            if kind == "gossip" and egid:
                extra_parts.append(f"--egid {egid}")
            if resolved_cid:
                extra_parts.append(f"--cid {resolved_cid}")
            extra = f" {' '.join(extra_parts)}" if extra_parts else ""
            hints["next_command"] = (
                f"maimai comments {resolved_id} --kind {kind} --page {next_page} --limit {limit}{extra}"
            )

        emit_ok(
            data if raw else summarized,
            kind=kind,
            id=resolved_id,
            cid=resolved_cid or None,
            cid_resolved_from_short_index=bool(cid and cid.isdigit() and cid != resolved_cid),
            page=page,
            comment_short_index_count=len(entries),
            **hints,
            as_json=as_json,
            as_yaml=as_yaml,
        )

    run_with_client(action, as_json=as_json, as_yaml=as_yaml, on_success=on_success)


@click.command()
@click.argument("mmid")
@click.option("--trackable-token", default="", help="Token from search/feed/profile links, when available.")
@click.option("--raw", is_flag=True, help="Print the full profile card. This may include personal data.")
@structured_output_options
def profile(
    mmid: str,
    trackable_token: str,
    raw: bool,
    as_json: bool,
    as_yaml: bool,
) -> None:
    """Read a visible profile/contact card. ``mmid`` can be a 1-based short index."""
    ref = refs.resolve_reference(mmid, expect_kind="contact")
    resolved_mmid = str(ref.get("mmid") or ref.get("id") or mmid)
    if mmid.isdigit() and not ref:
        emit_exception(
            MaimaiCliError(
                NOT_FOUND,
                f"Short index {mmid} not found. Run `maimai search` first.",
            ),
            as_json=as_json, as_yaml=as_yaml,
        )
        raise SystemExit(1)
    trackable_token = trackable_token or str(ref.get("trackable_token") or "")

    def action(client):
        return client.profile(resolved_mmid, trackable_token)

    def on_success(data):
        emit_ok(
            data if raw else summarize_profile(data),
            mmid=resolved_mmid,
            trackable_token_used=bool(trackable_token),
            as_json=as_json,
            as_yaml=as_yaml,
        )

    run_with_client(action, as_json=as_json, as_yaml=as_yaml, on_success=on_success)


@click.command("refs")
@click.option("--limit", default=20, show_default=True, help="Max entries to show.")
@click.option("--scope", type=click.Choice(["posts", "comments"]), default="posts", show_default=True, help="Which short-index cache to inspect.")
@structured_output_options
def refs_cmd(limit: int, scope: str, as_json: bool, as_yaml: bool) -> None:
    """Show the short-index reference cache from the last listing command."""
    ref_scope = "comments" if scope == "comments" else "default"
    index = refs.load_index(ref_scope)
    entries = index["entries"][:limit]
    indexed = [{"index": i + 1, **entry} for i, entry in enumerate(entries)]
    emit_ok(
        indexed,
        scope=scope,
        source_command=index["source_command"],
        saved_at=index["saved_at"],
        total=len(index["entries"]),
        as_json=as_json,
        as_yaml=as_yaml,
    )


@click.command("raw-get")
@click.argument("path")
def raw_get(path: str) -> None:
    """Personal debugging helper for a specific same-origin GET path."""
    if not path.startswith("/"):
        raise click.BadParameter("path must start with /")
    if not path.startswith(("/sdk/", "/web/", "/profile/", "/contact/", "/community/api/")):
        raise click.BadParameter("only limited same-origin paths are allowed")

    def action(client):
        resp = client.http.get(path)
        client._merge_cookies()
        content_type = resp.headers.get("content-type", "")
        if "application/json" in content_type:
            click.echo(json.dumps(resp.json(), ensure_ascii=False, indent=2))
        else:
            click.echo(resp.text[:4000])
        if resp.status_code >= 400:
            raise SystemExit(1)

    run_with_client(action)


def register(cli: click.Group) -> None:
    for command in (me, search, feed, hot_rank, company_feed, detail, comments, profile, refs_cmd, raw_get):
        cli.add_command(command)
