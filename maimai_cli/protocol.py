from __future__ import annotations

import re

BASE_URL = "https://maimai.cn"
LOGIN_PATH = "/platform/login"
COMMUNITY_ME_PATH = "/community/api/common/get-user-info"
COMMUNITY_SEARCH_PATH = "/community/api/common/search"

FEED_COMMENTS = "feed.comments"
FEED_LV2_COMMENTS = "feed.lv2_comments"
GOSSIP_COMMENTS = "gossip.comments"
GOSSIP_LV2_COMMENTS = "gossip.lv2_comments"
WAY_FEED = "feed.way"
GOSSIP_LIST = "feed.gossip"
FOCUS_FEED = "feed.recommended"
FOLLOWING_FEED = "feed.following"
FRIEND_FEED = "feed.friend"

DEFAULT_ACTIONS: dict[str, str] = {
    FEED_COMMENTS: "7f2dcd145c1ec90f0b5a56bad177e2bc9a81f3f399",
    FEED_LV2_COMMENTS: "7f70e5560e6ac30c4d7fd36c0de033ca1d20de7661",
    GOSSIP_COMMENTS: "7fc63c1c19d643f2120e7e8f008aba0f4ff0160f31",
    GOSSIP_LV2_COMMENTS: "7f2ec33cb94077599b38d7957474e6b5b112bae7e0",
    WAY_FEED: "7f86b66a27f8a78f816f9898fc23df0643cbb4630d",
    GOSSIP_LIST: "7fe2e53468359097d2323f610fcc3a30387168fcf5",
    FOCUS_FEED: "7fa16f2aea3017e1adb4e7fded1324f6b037be7db4",
    FOLLOWING_FEED: "7fba886e5c9a4ef7f72f31334ca542ae330c9d52ca",
    FRIEND_FEED: "7fd37a382b27cf5adc1260ba5020af6f618c7f5e83",
}

FEED_ACTION_KEYS: dict[str, str] = {
    "recommended": FOCUS_FEED,
    "following": FOLLOWING_FEED,
    "friend": FRIEND_FEED,
    "gossip": GOSSIP_LIST,
    "work_exp": WAY_FEED,
    "interview_exp": WAY_FEED,
    "offer_choice": WAY_FEED,
}

ACTION_ID_RE = re.compile(r"(?<![0-9a-fA-F])(7f[0-9a-fA-F]{40})(?![0-9a-fA-F])")


def discover_action_ids(text: str) -> list[str]:
    """Return unique Next server action ids found in page/Flight text."""
    seen: set[str] = set()
    out: list[str] = []
    for match in ACTION_ID_RE.finditer(text):
        action_id = match.group(1).lower()
        if action_id in seen:
            continue
        seen.add(action_id)
        out.append(action_id)
    return out
