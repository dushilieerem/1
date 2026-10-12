import unittest
from services.community.community_store import _normalize_post_fields


class PostLimitsTest(unittest.TestCase):
    def normalize(self, body, draft=False, code=None):
        return _normalize_post_fields(title="测试", body=body, section="factor",
                                      code_snippet=code, author_role="user", as_draft=draft)

    def test_boundary_and_unicode(self):
        for char in ("中", "a", "😀"):
            for draft in (True, False):
                self.assertEqual(len(self.normalize(" " + char * 20000 + " ", draft)[1]), 20000)
                with self.assertRaisesRegex(ValueError, "20000"):
                    self.normalize(char * 20001, draft)

    def test_code_separate_and_required_content(self):
        self.assertEqual(self.normalize("", code="x" * 20001)[3], "x" * 20001)
        with self.assertRaisesRegex(ValueError, "不能同时为空"):
            self.normalize("  ")


if __name__ == "__main__":
    unittest.main()
