from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from maimai_cli import refs


class RefsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.patches = [
            mock.patch.object(refs, "INDEX_FILE", root / "refs.json"),
            mock.patch.object(refs, "COMMENT_INDEX_FILE", root / "comment_refs.json"),
            mock.patch.object(refs, "CONTEXT_FILE", root / "context.json"),
            mock.patch.object(
                refs,
                "_INDEX_FILES",
                {"default": root / "refs.json", "comments": root / "comment_refs.json"},
            ),
        ]
        for patcher in self.patches:
            patcher.start()
        refs.clear_all()

    def tearDown(self) -> None:
        refs.clear_all()
        for patcher in reversed(self.patches):
            patcher.stop()
        self.tmp.cleanup()

    def test_comment_scope_does_not_replace_post_scope(self) -> None:
        refs.save_index(
            [{"kind": "gossip", "id": "36750549", "egid": "egid-1", "label": "post"}],
            source_command="company-feed",
        )
        refs.save_index(
            [{"kind": "comment", "id": "c1", "label": "comment"}],
            source_command="comments 36750549 --kind gossip",
            scope="comments",
        )

        self.assertEqual(refs.resolve_reference("1", expect_kind="gossip")["id"], "36750549")
        self.assertEqual(refs.resolve_reference("1", expect_kind="gossip")["egid"], "egid-1")
        self.assertEqual(refs.resolve_reference("1", expect_kind="comment", scope="comments")["id"], "c1")

    def test_raw_numeric_id_keeps_cached_context_when_short_index_kind_differs(self) -> None:
        refs.cache_context("gossip", "36750549", {"kind": "gossip", "id": "36750549", "egid": "egid-1"})
        refs.save_index(
            [{"kind": "feed", "id": "36750549", "efid": "efid-1"}],
            source_command="feed",
        )

        resolved = refs.resolve_reference("36750549", expect_kind="gossip")
        self.assertEqual(resolved["id"], "36750549")
        self.assertEqual(resolved["egid"], "egid-1")


if __name__ == "__main__":
    unittest.main()
