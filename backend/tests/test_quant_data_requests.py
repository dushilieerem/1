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

    def test_delivered_rejects_unpublished_view(self):
        with self.assertRaisesRegex(ValueError, "不存在或未发布"):
            self._update("in_progress", {"status": "delivered", "delivered_view": "research-rv-20990101-0"})

    def test_delivered_rejects_definition_only_view(self):
        # 只有 YAML 定义、没有 materialized 发布产物的视图应拒绝交付。
        # 用 patch 固定「已发布集合」，不要依赖数据平台目录的实时内容：
        # 数据侧会清理旧 release，写死真实 view_id 的用例会跟着红。
        with patch.object(svc, "_published_views", return_value={"research-rv-20261106-3"}):
            with self.assertRaisesRegex(ValueError, "不存在或未发布"):
                self._update("in_progress", {"status": "delivered", "delivered_view": "research-rv-20261105-3"})


class ListRequestScopeTest(unittest.TestCase):
    def test_researcher_sees_own_requests_only(self):
        cursor = MagicMock()
        cursor.execute.return_value.fetchall.return_value = []
        with patch.object(svc, "get_conn", return_value=_conn(cursor)):
            svc.list_requests(9, 2)
        self.assertIn("r.user_id=%s", cursor.execute.call_args.args[0])
        self.assertEqual(cursor.execute.call_args.args[1], (2, 9))

    def test_manager_sees_org_requests(self):
        cursor = MagicMock()
        cursor.execute.return_value.fetchall.return_value = []
        with patch.object(svc, "get_conn", return_value=_conn(cursor)):
            svc.list_requests(9, 2, True)
        self.assertNotIn("r.user_id=%s", cursor.execute.call_args.args[0])
        self.assertEqual(cursor.execute.call_args.args[1], (2,))


class ViewUsageScopeTest(unittest.TestCase):
    # 数据平台会清理旧 release：用例固定「已发布集合」，不读实时目录。
    _VIEW = "research-rv-20261105-5"

    def test_researcher_usage_is_member_scoped(self):
        cursor = MagicMock()
        cursor.execute.return_value.fetchall.return_value = []
        with patch.object(svc, "_published_views", return_value={self._VIEW}), \
                patch.object(svc, "get_conn", return_value=_conn(cursor)):
            out = svc.view_usage(9, 2, "research-rv-20261105-5")
        self.assertEqual(out["view_id"], "research-rv-20261105-5")
        factor_params = cursor.execute.call_args_list[0].args[1]
        strategy_params = cursor.execute.call_args_list[1].args[1]
        self.assertEqual(factor_params, (2, "research-rv-20261105-5", 9))
        self.assertEqual(strategy_params, (2, "research-rv-20261105-5", 9))

    def test_manager_usage_is_org_scoped(self):
        cursor = MagicMock()
        cursor.execute.return_value.fetchall.return_value = []
        with patch.object(svc, "_published_views", return_value={self._VIEW}), \
                patch.object(svc, "get_conn", return_value=_conn(cursor)):
            svc.view_usage(9, 2, "research-rv-20261105-5", True)
        self.assertEqual(cursor.execute.call_args_list[0].args[1], (2, "research-rv-20261105-5"))
        self.assertEqual(cursor.execute.call_args_list[1].args[1], (2, "research-rv-20261105-5"))


if __name__ == "__main__":
    unittest.main()
