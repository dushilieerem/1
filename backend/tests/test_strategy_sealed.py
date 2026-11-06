import unittest
from unittest.mock import MagicMock, patch

from services import strategy_sealed as s


BRANCH = {"id": "b1", "topic_id": "t1", "owner_id": 7, "status": "active",
          "review_status": "", "reviewer_id": None, "version": 1, "hypothesis": "h"}
TOPIC = {"id": "t1", "view_id": "v", "max_sealed": 1, "release_ids": {},
         "view_manifest_sha256": "", "contract_revision": "", "as_of": None,
         "validation_start": "2025-01-01", "validation_end": "2025-12-31"}


def _conn(fetchones):
    cursor = MagicMock(); cursor.execute.return_value = cursor
    cursor.fetchone.side_effect = list(fetchones)
    connection = MagicMock(); connection.__enter__.return_value = cursor
    return connection


class SealGateTest(unittest.TestCase):
    def test_complete_gate_required(self):
        with patch.object(s, "_branch_topic", return_value=(dict(BRANCH), dict(TOPIC))), \
             patch("services.strategy_sealed.published_view", return_value={"view_id": "v"}), \
             patch.object(s, "_latest_gate", return_value={"complete": True, "passed": False,
                                                          "checks": [{"name": "扣费后年化超额", "passed": False}]}), \
             patch.object(s, "get_conn", return_value=_conn([None, {"n": 0}])):
            with self.assertRaisesRegex(ValueError, "未全部通过"):
                s.request(1, 2, "b1", "k")


class ReviewTest(unittest.TestCase):
    def test_owner_cannot_review_own_branch(self):
        branch = dict(BRANCH, owner_id=7, status="submitted", reviewer_id=None)
        with patch.object(s, "_branch_topic", return_value=(branch, dict(TOPIC))):
            with self.assertRaisesRegex(ValueError, "自己"):
                s.claim(7, 2, "b1")

    def test_reviewer_must_claim_first(self):
        branch = dict(BRANCH, owner_id=7, status="submitted", reviewer_id=None)
        with patch.object(s, "_branch_topic", return_value=(branch, dict(TOPIC))):
            with self.assertRaisesRegex(ValueError, "领取"):
                s.decide(9, 2, "b1", "approved")
