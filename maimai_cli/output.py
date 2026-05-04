from __future__ import annotations

import json
import os
import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urlparse

import click
import yaml

SCHEMA_VERSION = "1"
_OUTPUT_ENV = "MAIMAI_OUTPUT"


def _resolve_format(as_json: bool = False, as_yaml: bool = False) -> str:
    """Resolve output format: explicit flag > env override > default (yaml)."""
    if as_json and as_yaml:
        raise click.UsageError("Use only one of --json or --yaml.")
    if as_json:
        return "json"
    if as_yaml:
        return "yaml"
    override = os.getenv(_OUTPUT_ENV, "").strip().lower()
    if override in {"json", "yaml"}:
        return override
    return "yaml"


def _dump(payload: dict, fmt: str) -> None:
    if fmt == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        click.echo(
            yaml.safe_dump(
                payload,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            ).rstrip()
        )


def emit(data: dict, *, as_json: bool = False, as_yaml: bool = False) -> None:
    """Back-compat emitter. Honors --json/--yaml when passed."""
    _dump(data, _resolve_format(as_json=as_json, as_yaml=as_yaml))


def emit_ok(
    data: dict | None = None,
    *,
    as_json: bool = False,
    as_yaml: bool = False,
    **extra: Any,
) -> None:
    """Emit a structured success payload.

    Top-level keys in ``extra`` are preserved alongside ``data`` so callers can
    surface fields like ``next_command``, ``next_offset``, ``has_more`` at the
    root of the payload for discoverability.
    """
    payload: dict[str, Any] = {"ok": True, "schema_version": SCHEMA_VERSION}
    payload.update(extra)
    if data is not None:
        payload["data"] = data
    _dump(payload, _resolve_format(as_json=as_json, as_yaml=as_yaml))


def emit_err(
    code: str,
    message: str,
    *,
    as_json: bool = False,
    as_yaml: bool = False,
    details: Any | None = None,
) -> None:
    """Emit a structured error payload with a stable ``error_code``."""
    payload: dict[str, Any] = {
        "ok": False,
        "schema_version": SCHEMA_VERSION,
        "error_code": code,
        "error": message,
    }
    if details is not None:
        payload["details"] = details
    _dump(payload, _resolve_format(as_json=as_json, as_yaml=as_yaml))


def structured_output_options(command):
    """Decorator adding --json/--yaml flags to a click command."""
    command = click.option("--yaml", "as_yaml", is_flag=True, help="Force YAML output.")(command)
    command = click.option("--json", "as_json", is_flag=True, help="Force JSON output.")(command)
    return command


# ─── Pagination hints ──────────────────────────────────────────────────────


def make_pagination_hints(
    *,
    command: str,
    args: list[str],
    offset: int,
    limit: int,
    loaded: int,
    has_more: bool,
) -> dict[str, Any]:
    """Build next_offset / next_page / next_command hints for list commands.

    ``args`` should be the positional arguments (e.g. ["feed"] or
    ["company-feed", "<webcid>"]). Flags like --offset/--limit are appended by
    this helper.
    """
    hints: dict[str, Any] = {"has_more": bool(has_more)}
    if not has_more or loaded == 0:
        return hints
    next_offset = offset + loaded
    next_page = (next_offset // limit) + 1 if limit else None
    hints["next_offset"] = next_offset
    if next_page is not None:
        hints["next_page"] = next_page
    arg_str = " ".join(args)
    hints["next_command"] = (
        f"maimai {command} {arg_str} --offset {next_offset} --limit {limit}".strip()
    )
    return hints


def clean_text(value: object, *, max_len: int = 260) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"<dref\b[^>]*>(.*?)</dref>", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "..."
    return text


def action_counts(item: dict) -> dict:
    common = item.get("common", {}) if isinstance(item, dict) else {}
    action_bar = common.get("action_bar", {}) if isinstance(common, dict) else {}
    return {
        "likes": action_bar.get("like_cnt") if action_bar else item.get("likes"),
        "shares": action_bar.get("share_cnt") if action_bar else item.get("spreads"),
        "comments": action_bar.get("comment_cnt") if action_bar else item.get("cmts") or item.get("total_cnt"),
    }


def egid_from_target(item: dict) -> str:
    target = item.get("target") or item.get("config", {}).get("target", "")
    query = parse_qs(urlparse(target).query)
    return (query.get("egid") or [""])[0]


def summarize_me(payload: dict) -> dict:
    user = payload.get("user", {}) if isinstance(payload, dict) else {}
    if not isinstance(user, dict):
        user = {}
    return {
        "result": payload.get("result"),
        "user": {
            "id": user.get("id"),
            "username": user.get("username"),
            "company": user.get("company") or user.get("std_company"),
            "position": user.get("position"),
            "city": user.get("city"),
            "profile_complete": user.get("info_ratio"),
        },
        "available_sections": sorted(
            key for key in user.keys()
            if key in {"work_exp", "education", "user_stat", "alerts", "config"}
        ),
    }


def summarize_feed_item(item: dict) -> dict:
    if not isinstance(item, dict):
        return {"value": clean_text(item)}
    if isinstance(item.get("feed"), dict):
        feed = item["feed"]
        contact = item.get("contact", {}) if isinstance(item.get("contact"), dict) else {}
        return {
            "kind": "feed",
            "id": feed.get("id") or item.get("fid"),
            "efid": item.get("efid") or feed.get("efid"),
            "title": clean_text(feed.get("title") or feed.get("summary"), max_len=120),
            "text": clean_text(feed.get("text")),
            "author": {
                "name": contact.get("name"),
                "mmid": contact.get("mmid") or contact.get("id"),
                "company": contact.get("company"),
                "position": contact.get("position"),
                "trackable_token": contact.get("trackable_token"),
            },
            "counts": action_counts(feed),
            "time": feed.get("crtime_string") or feed.get("crtime"),
        }
    if isinstance(item.get("style44"), dict) or isinstance(item.get("style35"), dict):
        style = item["style44"] if isinstance(item.get("style44"), dict) else item["style35"]
        author = style.get("author_info", {}) if isinstance(style.get("author_info"), dict) else {}
        return {
            "kind": "gossip",
            "id": style.get("id") or str(item.get("id", "")).removeprefix("gossip_"),
            "egid": style.get("egid") or egid_from_target(item),
            "title": clean_text(style.get("title"), max_len=120),
            "text": clean_text(style.get("text")),
            "author": {
                "name": author.get("name"),
                "company_position": author.get("compos") or clean_text(
                    f"{author.get('company', '')}{author.get('position', '')}", max_len=80
                ),
            },
            "counts": action_counts(item),
            "time": style.get("last_modify_time") or style.get("time"),
        }
    if item.get("egid"):
        author = item.get("author_info", {}) if isinstance(item.get("author_info"), dict) else {}
        return {
            "kind": "gossip",
            "id": item.get("id"),
            "egid": item.get("egid"),
            "title": clean_text(item.get("title"), max_len=120),
            "text": clean_text(item.get("text")),
            "author": {
                "name": author.get("name") or item.get("name"),
                "company_position": author.get("compos") or clean_text(
                    f"{author.get('company', '')}{author.get('position', '')}", max_len=80
                ),
            },
            "counts": action_counts(item),
            "time": item.get("last_modify_time") or item.get("time"),
        }
    if isinstance(item.get("style1"), dict):
        style = item["style1"]
        header = style.get("header", {}) if isinstance(style.get("header"), dict) else {}
        return {
            "kind": "feed",
            "id": item.get("id"),
            "efid": item.get("efid"),
            "title": clean_text(style.get("title"), max_len=120),
            "text": clean_text(style.get("text") or style.get("copy_text")),
            "author": {
                "name": header.get("name") or clean_text(header.get("title"), max_len=80),
                "desc": clean_text(header.get("desc"), max_len=80),
                "profile": header.get("target"),
            },
            "counts": action_counts(item),
            "time": header.get("time_subtitle") or style.get("last_modify_time"),
        }
    return {
        "kind": "unknown",
        "id": item.get("id"),
        "title": clean_text(item.get("title"), max_len=120),
        "text": clean_text(item.get("text")),
        "counts": action_counts(item),
    }


def summarize_search(payload: dict, limit: int) -> dict:
    feeds = payload.get("feeds", {}).get("feeds", []) if isinstance(payload.get("feeds"), dict) else []
    gossips = payload.get("gossips", {}).get("gossips", []) if isinstance(payload.get("gossips"), dict) else []
    contacts = payload.get("contacts", {}).get("contacts", []) if isinstance(payload.get("contacts"), dict) else []
    return {
        "feeds": [summarize_feed_item(item) for item in feeds[:limit]],
        "gossips": [summarize_feed_item({"style44": item.get("gossip", {}), "id": item.get("gid")}) for item in gossips[:limit]],
        "contacts": [
            {
                "name": contact.get("name"),
                "mmid": contact.get("mmid") or contact.get("id"),
                "company": contact.get("company"),
                "position": contact.get("position"),
                "city": contact.get("city") or contact.get("loc"),
                "trackable_token": contact.get("trackable_token"),
            }
            for contact in contacts[:limit]
            if isinstance(contact, dict)
        ],
    }


def summarize_comment(comment: dict) -> dict:
    user = comment.get("u", {}) if isinstance(comment.get("u"), dict) else {}
    replies = comment.get("cmt", []) if isinstance(comment.get("cmt"), list) else []
    return {
        "id": comment.get("id"),
        "text": clean_text(comment.get("t") or comment.get("rt")),
        "author": {
            "name": user.get("name"),
            "mmid": user.get("mmid") or user.get("id"),
            "company_position": user.get("compos"),
            "trackable_token": user.get("trackable_token"),
        },
        "likes": comment.get("likes"),
        "reply_count": comment.get("n"),
        "replies": [summarize_comment(reply) for reply in replies[:2]],
        "time": comment.get("time_str"),
        "ip_loc": comment.get("ip_loc"),
    }


def summarize_comments(payload: dict, limit: int) -> dict:
    comments = payload.get("comments") if isinstance(payload.get("comments"), dict) else payload
    items = comments.get("lst", []) if isinstance(comments, dict) else []
    return {
        "items": [summarize_comment(item) for item in items[:limit] if isinstance(item, dict)],
        "has_more": bool(comments.get("more")) if isinstance(comments, dict) else False,
    }


def summarize_profile(card: dict) -> dict:
    work_exp = card.get("work_exp", []) if isinstance(card.get("work_exp"), list) else []
    education = card.get("education", []) if isinstance(card.get("education"), list) else []
    return {
        "id": card.get("id") or card.get("mmid"),
        "name": card.get("name") or card.get("realname"),
        "headline": clean_text(card.get("headline") or card.get("compos"), max_len=160),
        "company": card.get("company") or card.get("std_company"),
        "position": card.get("position"),
        "city": card.get("city"),
        "work_exp": [
            {
                "company": item.get("company") or item.get("company_name"),
                "position": item.get("position"),
                "time": clean_text(item.get("time") or item.get("duration"), max_len=80),
            }
            for item in work_exp[:5]
            if isinstance(item, dict)
        ],
        "education": [
            {
                "school": item.get("school") or item.get("school_name"),
                "major": item.get("major"),
                "degree": item.get("degree"),
            }
            for item in education[:3]
            if isinstance(item, dict)
        ],
    }


def summarize_company_circle(circle: dict) -> dict:
    return {
        "name": circle.get("circle_name"),
        "member_count": circle.get("member_cnt"),
        "discuss_count": circle.get("discuss_cnt"),
        "visit_rank": circle.get("visit_rank"),
        "recent_visits_7d": circle.get("current_recent_visit"),
        "weekly_active_users": circle.get("wau"),
        "cid": circle.get("d_cid"),
    }
