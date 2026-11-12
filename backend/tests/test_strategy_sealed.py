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


class ReviewDecisionTest(unittest.TestCase):
    def _branch(self, **kw):
        return {**BRANCH, "owner_id": 7, "reviewer_id": 9, "status": "submitted", **kw}

    def test_approve_requires_passed_gate(self):
        with patch.object(s, "_branch_topic", return_value=(self._branch(), dict(TOPIC))), \
             patch.object(s, "_latest_gate", return_value={"passed": False, "complete": True}), \
             patch.object(s, "get_conn"), patch.object(s, "_event"):
            with self.assertRaisesRegex(ValueError, "不能入库"):
                s.decide(9, 2, "b1", "approved", "ok")

    def test_approve_writes_status_and_event(self):
        cursor = MagicMock(); cursor.execute.return_value = cursor
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(s, "_branch_topic", side_effect=[
                (self._branch(), dict(TOPIC)), (self._branch(status="approved"), dict(TOPIC))]), \
             patch.object(s, "_latest_gate", return_value={"passed": True, "complete": True}), \
             patch.object(s, "get_conn", return_value=connection), \
             patch.object(s, "_event") as ev:
            out = s.decide(9, 2, "b1", "approved", "证据齐全")
        self.assertEqual(out["status"], "approved")
        self.assertEqual(ev.call_args.args[4], "approve")

    def test_reject_needs_no_gate(self):
        cursor = MagicMock(); cursor.execute.return_value = cursor
        connection = MagicMock(); connection.__enter__.return_value = cursor
        with patch.object(s, "_branch_topic", side_effect=[
                (self._branch(), dict(TOPIC)), (self._branch(status="rejected"), dict(TOPIC))]), \
             patch.object(s, "get_conn", return_value=connection), patch.object(s, "_event") as ev:
            out = s.decide(9, 2, "b1", "rejected", "证据不足")
        self.assertEqual(out["status"], "rejected")
        self.assertEqual(ev.call_args.args[4], "reject")

    def test_submit_requires_sealed_passed(self):
        for review_status in ("", "seal_failed"):
            with patch.object(s, "_branch_topic", return_value=(self._branch(), dict(TOPIC))):
                with patch.object(s, "_branch_topic", return_value=(self._branch(status="frozen", review_status=review_status), dict(TOPIC))):
                    with self.assertRaisesRegex(ValueError, "封存通过"):
                        s.submit_for_review(7, 2, "b1")
