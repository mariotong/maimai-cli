from __future__ import annotations

import json
import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .actions import ActionRegistry
from .config import cookie_header
from .protocol import (
    BASE_URL,
    COMMUNITY_ME_PATH,
    COMMUNITY_SEARCH_PATH,
    FEED_ACTION_KEYS,
    FEED_COMMENTS,
    FEED_LV2_COMMENTS,
    GOSSIP_COMMENTS,
    GOSSIP_LV2_COMMENTS,
    LOGIN_PATH,
    discover_action_ids,
)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/145.0.0.0 Safari/537.36"
)


class MaimaiError(RuntimeError):
    pass


class MaimaiClient:
    def __init__(self, cookies: dict[str, str] | None = None, timeout: float = 30.0):
        self.cookies = dict(cookies or {})
        self.actions = ActionRegistry()
        headers = {
            "user-agent": USER_AGENT,
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "origin": BASE_URL,
            "referer": f"{BASE_URL}{LOGIN_PATH}",
        }
        if self.cookies:
            headers["cookie"] = cookie_header(self.cookies)
        self.http = httpx.Client(
            base_url=BASE_URL,
            headers=headers,
            timeout=timeout,
            follow_redirects=True,
        )

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "MaimaiClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _merge_cookies(self) -> None:
        for cookie in self.http.cookies.jar:
            if "maimai.cn" in (cookie.domain or ""):
                self.cookies[cookie.name] = cookie.value

    def _get_json(self, path: str, **kwargs: Any) -> dict[str, Any]:
        resp = self.http.get(path, **kwargs)
        self._merge_cookies()
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MaimaiError(f"HTTP {resp.status_code} from {path}") from exc
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise MaimaiError(f"Non-JSON response from {path}: {resp.text[:200]}") from exc
        if not isinstance(data, dict):
            raise MaimaiError(f"Unexpected response from {path}: {data!r}")
        return data

    def status_probe(self) -> dict[str, Any]:
        """Return conservative login evidence without scraping private data."""
        resp = self.http.get("/", headers={"accept": "text/html,*/*"})
        self._merge_cookies()
        community_api_ok = False
        try:
            data = self._get_json(
                COMMUNITY_ME_PATH,
                params={"__platform": "community_web"},
                headers={
                    "accept": "*/*",
                    "referer": f"{BASE_URL}/community/home/recommended",
                    "sec-fetch-site": "same-origin",
                },
            )
            community_api_ok = data.get("result") == "ok" and isinstance(data.get("user"), dict)
        except MaimaiError:
            community_api_ok = False
        return {
            "http_status": resp.status_code,
            "has_saved_cookies": bool(self.cookies),
            "cookie_names": sorted(self.cookies.keys()),
            "community_api_ok": community_api_ok,
            "looks_logged_in": community_api_ok or ("登录/注册" not in resp.text and "loginBtn" not in resp.text),
        }

    def community_user_info(self) -> dict[str, Any]:
        data = self._get_json(
            COMMUNITY_ME_PATH,
            params={"__platform": "community_web"},
            headers={
                "accept": "*/*",
                "referer": f"{BASE_URL}/community/home/recommended",
                "sec-fetch-site": "same-origin",
            },
        )
        return data

    def search(self, query: str, *, limit: int = 4, offset: int = 0) -> dict[str, Any]:
        params: dict[str, Any] = {
            "frm": "website",
            "query": query,
            "__platform": "community_web",
            "lim": limit,
        }
        if offset:
            # The web result embeds search_qs with o=<offset>, but the current
            # endpoint appears to ignore it. Keep it explicit for compatibility
            # and let the command surface support status to callers.
            params["o"] = offset
        return self._get_json(
            COMMUNITY_SEARCH_PATH,
            params=params,
            headers={
                "accept": "*/*",
                "referer": f"{BASE_URL}/community/home/recommended",
                "sec-fetch-site": "same-origin",
            },
        )

    def community_page(self, path: str) -> str:
        return self._community_page_response(path).text

    def _community_page_response(self, path: str) -> httpx.Response:
        resp = self.http.get(
            path,
            headers={
                "accept": "text/html,*/*",
                "referer": f"{BASE_URL}/community/home/recommended",
            },
        )
        self._merge_cookies()
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MaimaiError(f"HTTP {resp.status_code} from {path}") from exc
        return resp

    def feed(self, feed_type: str = "recommended", *, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        if limit < 1:
            raise MaimaiError("limit must be >= 1.")
        if offset < 0:
            raise MaimaiError("offset must be >= 0.")
        html = self.community_page(f"/community/home/{feed_type}")
        flight = next_flight_text(html)
        discovered_actions = discover_action_ids(f"{html}\n{flight}")
        items = extract_json_value_after(flight, '"listDefault":')
        if not isinstance(items, list):
            raise MaimaiError(f"Could not find feed list for {feed_type}.")
        has_more = '"hasMoreDefault":true' in flight
        page = 1
        need_count = offset + limit
        while has_more and len(items) < need_count:
            data = self.feed_page(feed_type, page, discovered_actions=discovered_actions)
            append_list = data.get("data") if feed_type == "gossip" else data.get("feeds")
            if not isinstance(append_list, list) or not append_list:
                has_more = False
                break
            items.extend(append_list)
            has_more = bool(data.get("remain"))
            page += 1
        return {
            "list": items[offset:need_count],
            "list_type": feed_type,
            "has_more": has_more,
            "loaded_total": len(items),
            "offset": offset,
            "limit": limit,
        }

    def feed_page(
        self,
        feed_type: str,
        page: int,
        *,
        discovered_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"page": page}
        action_key = FEED_ACTION_KEYS.get(feed_type)
        if not action_key:
            raise MaimaiError(f"Pagination is not implemented for feed type {feed_type}.")
        if feed_type in {"work_exp", "interview_exp", "offer_choice"}:
            payload["custom_sub_tab_name"] = feed_type
        return self._server_action(
            action_key,
            f"/community/home/{feed_type}",
            [payload],
            referer=f"{BASE_URL}/community/home/{feed_type}",
            discovered_actions=discovered_actions,
        )

    def hot_rank(self) -> dict[str, Any]:
        html = self.community_page("/community/hot-rank")
        flight = next_flight_text(html)
        items = extract_json_value_after(flight, '"listDefault":')
        if not isinstance(items, list):
            raise MaimaiError("Could not find hot rank list.")
        return {"list": items, "has_more": '"hasMoreDefault":true' in flight}

    def resolve_company_webcid(self) -> str:
        """Resolve the current user's default company gossip circle id."""
        webcid = ""
        for path in ("/company/gossip_discuss", "/community/home/gossip", "/community/home/recommended", "/"):
            try:
                resp = self._community_page_response(path)
            except MaimaiError:
                continue
            webcid = webcid_from_url(str(resp.url)) or webcid_from_html(resp.text)
            if webcid:
                break
        if not webcid:
            raise MaimaiError("Could not resolve company webcid from visible community pages.")
        return webcid

    def company_feed(self, webcid: str = "", *, limit: int = 10, offset: int = 0) -> dict[str, Any]:
        webcid = webcid or self.resolve_company_webcid()
        html = self.community_page(f"/company/gossip_discuss?{urlencode({'webcid': webcid})}")
        share_data = share_data_from_html(html)
        payload = share_data.get("data")
        if not isinstance(payload, dict):
            raise MaimaiError(f"Could not parse company feed for {webcid}.")
        items = payload.get("data")
        if not isinstance(items, list):
            raise MaimaiError(f"Could not find company feed list for {webcid}.")
        circle_top = payload.get("circle_top") if isinstance(payload.get("circle_top"), dict) else {}
        auth_info = share_data.get("auth_info") if isinstance(share_data.get("auth_info"), dict) else {}
        if limit < 1:
            raise MaimaiError("limit must be >= 1.")
        if offset < 0:
            raise MaimaiError("offset must be >= 0.")
        pagination_error = ""
        has_more = bool(payload.get("remain"))
        first_page_count = len(items)
        if offset < first_page_count:
            window = items[offset:offset + limit]
            next_page = 1
        else:
            window = []
            next_page = ((offset - first_page_count) // 20) + 1
        skip_in_next_page = max(offset - first_page_count, 0) % 20
        seen = {str(item.get("id")) for item in window if isinstance(item, dict) and item.get("id")}
        loaded_total = max(first_page_count, offset)

        while has_more and len(window) < limit:
            try:
                page_payload = self.company_feed_page(webcid, page=next_page, count=20, auth_info=auth_info)
            except MaimaiError as exc:
                pagination_error = str(exc)
                break

            page_items = page_payload.get("data")
            if not isinstance(page_items, list) or not page_items:
                has_more = False
                break

            candidates = page_items[skip_in_next_page:]
            skip_in_next_page = 0
            loaded_total = first_page_count + next_page * 20
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "")
                if item_id and item_id in seen:
                    continue
                if item_id:
                    seen.add(item_id)
                window.append(item)
                if len(window) >= limit:
                    break

            has_more = bool(page_payload.get("remain"))
            next_page += 1

        return {
            "list": window,
            "loaded_total": offset + len(window),
            "fetched_until": max(loaded_total, offset + len(window)),
            "offset": offset,
            "limit": limit,
            "remain": payload.get("remain"),
            "count": payload.get("count"),
            "result": payload.get("result"),
            "circle": circle_top,
            "webcid": webcid,
            "has_more": has_more,
            "pagination_error": pagination_error,
        }

    def company_feed_page(
        self,
        webcid: str,
        *,
        page: int = 1,
        count: int = 20,
        auth_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Fetch the old React company-circle loadMore endpoint.

        The front-end bundle builds this URL as:
        /groundhog/gossip/v3/feed?webcid=<webcid>&...auth_info&page=<nextPage>&count=20
        where nextPage starts at 1 because the SSR page already contains the
        first 10 items.
        """
        query: dict[str, Any] = {"webcid": webcid}
        if auth_info:
            for key in ("u", "channel", "version", "_csrf", "_csrf_token"):
                if auth_info.get(key):
                    query[key] = auth_info[key]
        if "_csrf_token" not in query and self.cookies.get("csrftoken"):
            query["_csrf_token"] = self.cookies["csrftoken"]
        path = f"/groundhog/gossip/v3/feed?{urlencode({**query, 'page': page, 'count': count})}"
        headers = {
            "accept": "application/json, text/plain, */*",
            "referer": f"{BASE_URL}/company/gossip_discuss?{urlencode({'webcid': webcid})}",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "x-requested-with": "XMLHttpRequest",
        }
        csrf = self.cookies.get("csrftoken")
        if csrf:
            headers["x-csrf-token"] = csrf
        resp = self.http.get(path, headers=headers)
        self._merge_cookies()
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MaimaiError(f"HTTP {resp.status_code} from {path}") from exc
        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise MaimaiError(f"Non-JSON response from {path}: {resp.text[:200]}") from exc
        if not isinstance(data, dict):
            raise MaimaiError(f"Unexpected response from {path}: {data!r}")
        return data

    def feed_detail(self, fid: str, efid: str) -> dict[str, Any]:
        query = urlencode({"efid": efid, "fid": fid})
        path = f"/community/feed-detail/{fid}?{query}"
        html = self.community_page(path)
        detail = extract_json_value_after(next_flight_text(html), '"feedData":')
        if not isinstance(detail, dict):
            raise MaimaiError(f"Could not parse feed detail for {fid}.")
        return detail

    def gossip_detail(self, gid: str, egid: str) -> dict[str, Any]:
        query = urlencode({"egid": egid, "gid": gid})
        path = f"/community/gossip-detail/{gid}?{query}"
        html = self.community_page(path)
        flight = next_flight_text(html)
        for value in extract_json_values_after(flight, '"data":'):
            if isinstance(value, dict) and str(value.get("id")) == str(gid) and value.get("egid"):
                return value
        raise MaimaiError(f"Could not parse gossip detail for {gid}.")

    def profile(self, mmid: str, trackable_token: str = "") -> dict[str, Any]:
        query = {"dstu": mmid, "from": "maimai_cli"}
        if trackable_token:
            query["trackable_token"] = trackable_token
        html = self.community_page(f"/profile/detail?{urlencode(query)}")
        data = share_data_from_html(html)
        card = data.get("data", {}).get("card") if isinstance(data.get("data"), dict) else None
        if not isinstance(card, dict):
            raise MaimaiError(f"Could not parse profile card for {mmid}.")
        return card

    def comments(
        self,
        *,
        kind: str,
        item_id: str,
        page: int = 0,
        efid: str = "",
        egid: str = "",
        cid: str = "",
    ) -> dict[str, Any]:
        if kind == "feed":
            action_key = FEED_LV2_COMMENTS if cid else FEED_COMMENTS
            payload: dict[str, Any] = {"fid": item_id, "page": page}
            if cid:
                payload["cid"] = cid
            referer = f"{BASE_URL}/community/feed-detail/{item_id}?{urlencode({'efid': efid, 'fid': item_id})}"
            path = f"/community/feed-detail/{item_id}"
        elif kind == "gossip":
            if not egid:
                raise MaimaiError("gossip comments require --egid.")
            action_key = GOSSIP_LV2_COMMENTS if cid else GOSSIP_COMMENTS
            payload = {"egid": egid, "page": page}
            if cid:
                payload["cid"] = cid
            else:
                payload["gid"] = item_id
            referer = f"{BASE_URL}/community/gossip-detail/{item_id}?{urlencode({'egid': egid, 'gid': item_id})}"
            path = f"/community/gossip-detail/{item_id}"
        else:
            raise MaimaiError("kind must be feed or gossip.")
        return self._server_action(action_key, path, [payload], referer=referer)

    def _server_action(
        self,
        action_key: str,
        path: str,
        payload: list[Any],
        *,
        referer: str,
        discovered_actions: list[str] | None = None,
    ) -> dict[str, Any]:
        candidates = self.actions.candidates(action_key, discovered_actions)
        last_error: MaimaiError | None = None
        for action_id in candidates:
            try:
                data = self._post_server_action(path, action_id, payload, referer=referer)
            except MaimaiError as exc:
                last_error = exc
                continue
            self.actions.remember_success(action_key, action_id)
            return data

        if discovered_actions is None:
            page_html = self.community_page(path)
            discovered_actions = discover_action_ids(f"{page_html}\n{next_flight_text(page_html)}")
            for action_id in self.actions.candidates(action_key, discovered_actions):
                try:
                    data = self._post_server_action(path, action_id, payload, referer=referer)
                except MaimaiError as exc:
                    last_error = exc
                    continue
                self.actions.remember_success(action_key, action_id, source="runtime_discovery")
                return data

        if last_error:
            raise last_error
        raise MaimaiError(f"No action id candidates for {action_key}.")

    def _post_server_action(
        self,
        path: str,
        action_id: str,
        payload: list[Any],
        *,
        referer: str,
    ) -> dict[str, Any]:
        resp = self.http.post(
            path,
            headers={
                "accept": "text/x-component",
                "content-type": "text/plain;charset=UTF-8",
                "next-action": action_id,
                "referer": referer,
            },
            content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )
        self._merge_cookies()
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise MaimaiError(f"HTTP {resp.status_code} from server action") from exc
        data = parse_server_action_response(resp.text)
        if data is None:
            raise MaimaiError(f"Could not parse server action response: {resp.text[:200]}")
        return data


def next_flight_text(html: str) -> str:
    chunks: list[str] = []
    pattern = re.compile(r"self\.__next_f\.push\((.*?)\)</script>", re.DOTALL)
    for match in pattern.finditer(html):
        try:
            payload = json.loads(unescape(match.group(1)))
        except json.JSONDecodeError:
            continue
        if len(payload) > 1 and isinstance(payload[1], str):
            chunks.append(payload[1])
    return "".join(chunks)


def extract_json_value_after(text: str, key: str) -> Any:
    values = extract_json_values_after(text, key, limit=1)
    return values[0] if values else None


def extract_json_values_after(text: str, key: str, limit: int | None = None) -> list[Any]:
    decoder = json.JSONDecoder()
    values: list[Any] = []
    start = 0
    while True:
        idx = text.find(key, start)
        if idx < 0:
            return values
        value_start = idx + len(key)
        while value_start < len(text) and text[value_start].isspace():
            value_start += 1
        try:
            value, end = decoder.raw_decode(text[value_start:])
        except json.JSONDecodeError:
            start = value_start + 1
            continue
        values.append(value)
        if limit and len(values) >= limit:
            return values
        start = value_start + end


def share_data_from_html(html: str) -> dict[str, Any]:
    match = re.search(r"share_data\s*=\s*JSON\.parse\(\"(.*?)\"\);", html)
    if not match:
        raise MaimaiError("Could not find share_data in profile page.")
    try:
        decoded = json.loads(f'"{match.group(1)}"')
        data = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise MaimaiError("Could not decode share_data.") from exc
    if not isinstance(data, dict):
        raise MaimaiError("Unexpected share_data payload.")
    return data


def webcid_from_url(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    return (query.get("webcid") or [""])[0]


def webcid_from_html(html: str) -> str:
    try:
        share_data = share_data_from_html(html)
    except MaimaiError:
        share_data = {}
    for value in walk_json_values(share_data):
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{6,64}", value):
            if value.startswith("webcid="):
                return value.split("=", 1)[1]
        if isinstance(value, str) and "webcid=" in value:
            found = webcid_from_url(value)
            if found:
                return found

    for pattern in (
        r"[?&]webcid=([A-Za-z0-9_-]+)",
        r"webcid=([A-Za-z0-9_-]+)",
        r'"webcid"\s*:\s*"([A-Za-z0-9_-]+)"',
        r"'webcid'\s*:\s*'([A-Za-z0-9_-]+)'",
    ):
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return ""


def walk_json_values(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_json_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json_values(child)
    else:
        yield value


def parse_server_action_response(text: str) -> dict[str, Any] | None:
    data: dict[str, Any] | None = None
    for line in text.splitlines():
        match = re.match(r"^\d+:(.*)$", line)
        if not match:
            continue
        raw = match.group(1)
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "b" not in value:
            data = value
    return data
