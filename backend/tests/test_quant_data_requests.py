import unittest
from unittest.mock import MagicMock, patch

from services import quant_data_resources as svc


def _conn(cursor):
    conn = MagicMock()
    conn.__enter__.return_value = cursor
    return conn


class SubmitRequestTest(unittest.TestCase):
    def test_invalid_related_object_is_rejected(self):
        cursor = MagicMock()
        cursor.execute.return_value.fetchone.return_value = None
        with patch.object(svc, "get_conn", return_value=_conn(cursor)):
            with self.assertRaisesRegex(ValueError, "关联对象"):
                svc.submit_request(9, 2, {"title": "需要个股资金流", "related_type": "factor_topic", "related_id": "nope"})

    def test_submit_records_frequency_and_relation(self):
        cursor = MagicMock()
        cursor.execute.return_value.fetchone.return_value = {
            "id": "r1", "user_id": 9, "org_id": 2, "title": "需要个股资金流",
            "status": "submitted", "frequency": "日频", "related_type": "strategy_topic",
            "related_id": "s1"}
        with patch.object(svc, "get_conn", return_value=_conn(cursor)):
            out = svc.submit_request(9, 2, {
                "title": "需要个股资金流", "frequency": "日频",
                "related_type": "strategy_topic", "related_id": "s1",
            })
        self.assertNotIn("user_id", out)
        params = cursor.execute.call_args_list[1].args[1]
        self.assertEqual(params[6], "日频")
        self.assertEqual(params[8], "strategy_topic")


class UpdateRequestTest(unittest.TestCase):
    def _update(self, status, payload):
        cursor = MagicMock()
        cursor.execute.return_value.fetchone.return_value = {"id": "r1", "org_id": 2, "status": status}
        with patch.object(svc, "get_conn", return_value=_conn(cursor)):
            return svc.update_request(9, 2, "r1", payload)

    def test_rejects_illegal_transition(self):
        with self.assertRaisesRegex(ValueError, "不能改为"):
            self._update("delivered", {"status": "in_progress"})

    def test_unsupported_requires_reason(self):
        with self.assertRaisesRegex(ValueError, "原因"):
            self._update("submitted", {"status": "unsupported"})

    def test_delivered_requires_view(self):
        with self.assertRaisesRegex(ValueError, "视图"):
            self._update("in_progress", {"status": "delivered"})


if __name__ == "__main__":
    unittest.main()
