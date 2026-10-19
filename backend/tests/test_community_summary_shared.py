import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from ai.gateway.llm_client import LlmError
from ai.runtime.skills import skill_summarize_post
from services.community.ai_summary import summarize_with_re


class SharedSummaryTest(unittest.TestCase):
    def invoke(self, status=200, data=None, **kwargs):
        data = data if data is not None else {"summary_source": "llm", "summary_md": "## 结论\n仅供测试的归纳。", "tokens_in": 12, "tokens_out": 5, "model": "shared-model"}
        forward = MagicMock(return_value=(status, {}, data))
        with patch("services.community.ai_summary.env", return_value="http://internal-re.test"), patch.dict(sys.modules, {"services.core.re_http_gateway": SimpleNamespace(forward_re=forward)}):
            result = summarize_with_re(title="虚构记录", body="仅供测试的原文", code_snippet="", grounding={}, truncated=False, **kwargs)
        return result, forward

    def test_existing_re_connection_used_without_model_key_or_local_llm(self):
        result, forward = self.invoke()
        self.assertEqual(result["model"], "shared-model")
        self.assertEqual(result["tokens_in"], 12)
        self.assertEqual(forward.call_args.args, ("POST", "/api/ai/post-summaries"))
        payload = forward.call_args.kwargs["payload"]
        self.assertNotIn("api_key", payload)
        self.assertNotIn("base_url", payload)

    def test_shared_llm_output_is_marked_ai_and_usage_preserved(self):
        response = {"summary_md": "## 结论\n仅供测试的归纳。", "model": "shared", "tokens_in": 32, "tokens_out": 12, "truncated": False, "provider": "openai_compatible"}
        with patch("ai.runtime.skills.llm_configured", return_value=False), patch("ai.runtime.skills.summarize_with_re", return_value=response) as shared:
            result = skill_summarize_post({"title": "虚构测试", "body": "<p>测试内容<img src='data:image/png;base64,FAKE'></p>"}, {})
        self.assertEqual(result["board_patch"]["artifacts"]["summary_source"], "llm")
        self.assertEqual(result["tokens_in"], 32)
        self.assertNotIn("base64", shared.call_args.kwargs["body"])

    def test_explicit_local_llm_still_wins(self):
        with patch("ai.runtime.skills.llm_configured", return_value=True), patch("ai.runtime.skills.summarize_with_re") as shared, patch("ai.runtime.skills.chat_completions", return_value={"content": '{"summary_md":"本地模型摘要"}', "tokens_in": 1, "tokens_out": 1}):
            result = skill_summarize_post({"body": "虚构测试正文"}, {})
        shared.assert_not_called()
        self.assertEqual(result["board_patch"]["artifacts"]["summary_source"], "llm")

    def test_missing_endpoint_timeout_and_invalid_source_never_become_ai_success(self):
        for status, data in [(404, {}), (504, {}), (503, {}), (200, {"summary_source": "mock_local", "summary_md": "原文"}), (200, {"summary_source": "llm", "summary_md": " "})]:
            with self.subTest(status=status, data=data):
                with self.assertRaises(LlmError) as error:
                    self.invoke(status, data)
                self.assertNotIn("ResearchEngine", str(error.exception))
                self.assertNotIn("post-summaries", str(error.exception))

    def test_content_limits_propagate_truncation(self):
        forward = MagicMock(return_value=(200, {}, {"summary_source": "llm", "summary_md": "截断摘要"}))
        with patch("services.community.ai_summary.env", return_value="http://re.test"), patch.dict(sys.modules, {"services.core.re_http_gateway": SimpleNamespace(forward_re=forward)}):
            result = summarize_with_re(title="t" * 600, body="b" * 21000, code_snippet="c" * 21000, grounding={}, truncated=False)
        payload = forward.call_args.kwargs["payload"]
        self.assertEqual((len(payload["title"]), len(payload["body"]), len(payload["code_snippet"])), (512, 20000, 20000))
        self.assertTrue(payload["truncated"] and result["truncated"])

    def test_only_local_environment_without_re_keeps_honest_excerpt(self):
        with patch("services.community.ai_summary.env", return_value=""):
            self.assertIsNone(summarize_with_re(title="", body="虚构文本", code_snippet="", grounding={}, truncated=False))


if __name__ == "__main__":
    unittest.main()
