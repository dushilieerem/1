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

    def test_html_images_and_entities(self):
        from services.community.content_limits import post_body_text
        image = '<img src="data:image/png;base64,' + "a" * 30000 + '">'
        html = "<p>" + "😀" * 20000 + "</p>" + image
        self.assertEqual(self.normalize(html)[1], html)
        with self.assertRaisesRegex(ValueError, "20000"):
            self.normalize("<p>" + "中" * 20001 + "</p>" + image)
        self.assertEqual(post_body_text("<p>&amp;😀<strong>中</strong></p>"), "&😀中")
        self.assertEqual(post_body_text("# 标题\n正文"), "# 标题\n正文")


if __name__ == "__main__":
    unittest.main()
