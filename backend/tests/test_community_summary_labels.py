import unittest
from unittest.mock import patch
from ai.runtime.skills import skill_summarize_post
from ai.gateway.llm_client import LlmError


class SummaryTest(unittest.TestCase):
    def test_unconfigured_short_content_is_honest_excerpt(self):
        with patch("ai.runtime.skills.llm_configured", return_value=False):
            result = skill_summarize_post({"title": "测试", "body": "很短的内容"}, {})
        self.assertEqual(result["board_patch"]["artifacts"]["summary_source"], "mock_local")
        self.assertIn("原文节选", result["outputs"]["summary_md"])
        self.assertNotIn("## 结论", result["outputs"]["summary_md"])
        codes = [f["code"] for f in result["outputs"]["flags"]]
        self.assertIn("summary_rule_based", codes)
        self.assertIn("summary_short_content", codes)

    def test_empty_content_rejected(self):
        with self.assertRaisesRegex(LlmError, "为空"):
            skill_summarize_post({"title": "只有标题", "body": "<p> </p>"}, {})

    def test_configured_model_and_failure(self):
        with patch("ai.runtime.skills.llm_configured", return_value=True), patch("ai.runtime.skills.chat_completions") as llm:
            llm.return_value = {"content": '{"summary_md":"依据原文生成的摘要"}', "tokens_in": 10, "tokens_out": 5}
            result = skill_summarize_post({"body": "这是用来验证模型路径的一段足够长的研究说明正文。"}, {})
            self.assertEqual(result["board_patch"]["artifacts"]["summary_source"], "llm")
            llm.side_effect = LlmError("模型超时")
            with self.assertRaisesRegex(LlmError, "模型超时"):
                skill_summarize_post({"body": "研究正文"}, {})


if __name__ == "__main__":
    unittest.main()
