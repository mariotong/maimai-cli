from __future__ import annotations

import unittest

from maimai_cli.client import webcid_from_html
from maimai_cli.protocol import discover_action_ids


class ProtocolTests(unittest.TestCase):
    def test_discover_action_ids_deduplicates(self) -> None:
        action_id = "7f2dcd145c1ec90f0b5a56bad177e2bc9a81f3f399"
        self.assertEqual(discover_action_ids(f"{action_id} {action_id}"), [action_id])

    def test_webcid_from_html_supports_deep_link(self) -> None:
        html = 'taoumaimai://rct?component=GossipCircle\\u0026webcid=abc_123'
        self.assertEqual(webcid_from_html(html), "abc_123")


if __name__ == "__main__":
    unittest.main()
