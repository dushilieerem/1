import unittest
from unittest.mock import patch
from services.community.community_store import create_report, create_comment


class ValidationTest(unittest.TestCase):
    def test_report_rejects_overflow_before_database(self):
        with patch("services.community.community_store.get_conn") as db:
            for target in ("post", "comment"):
                with self.assertRaisesRegex(ValueError, "500"):
                    create_report(1, target_type=target, post_id=16, comment_id=5,
                                  reason="spam", detail="😀" * 501)
            db.assert_not_called()

    def test_report_boundary_is_not_truncated(self):
        with patch("services.community.community_store.get_conn", side_effect=RuntimeError("db boundary")):
            with self.assertRaisesRegex(RuntimeError, "db boundary"):
                create_report(1, target_type="post", post_id=16, reason="spam", detail="😀" * 500)

    def test_comment_rejects_overflow_and_blank(self):
        with patch("services.community.community_store.get_conn") as db:
            for parent in (None, 5):
                for body in ("😀" * 2001, " \n "):
                    with self.assertRaises(ValueError):
                        create_comment(16, 1, body, parent_id=parent)
            db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
