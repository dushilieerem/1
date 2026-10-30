"""社区读帖摘要：RE 回退路径与响应契约（ADR-037 P1-1 后由路由层承载）。"""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai.errors import AiBadOutput, AiError, AiNotConfigured
from ai.gateway import providers
from ai.router import run_task
from ai.router.specs import TaskRequest
from ai.router.tasks.community_summary import (
    parse_re_summary,
    re_payload,
    validate_summary,
)
from ai.runtime.skills import skill_summarize_post

RE_RESPONSE = {
    "summary_source": "llm",
    "summary_md": "## 结论\n仅供测试的归纳。",
    "tokens_in": 12,
    "tokens_out": 5,
    "model": "shared-model",
}


class ReFallbackTest(unittest.TestCase):
    def invoke(self, status=200, data=None, variables=None):
        data = data if data is not None else dict(RE_RESPONSE)
        forward = MagicMock(return_value=(status, {}, data))
        variables = variables or {
            "title": "虚构记录",
            "body": "仅供测试的原文",
            "code_snippet": "",
            "grounding": {},
            "truncated": False,
        }
        with patch("services.core.env_config.env", return_value="http://internal-re.test"), patch.dict(
            sys.modules,
            {"services.core.re_http_gateway": SimpleNamespace(forward_re=forward)},
        ), patch.object(providers, "resolve_target", side_effect=AiNotConfigured("no key")):
            result = run_task(
                "community.summarize_post",
                messages=[{"role": "user", "content": "ignored"}],
                variables=variables,
            )
        return result, forward

    def test_local_missing_falls_back_to_research_service(self):
        result, forward = self.invoke()
        self.assertEqual(result["data"]["summary_md"], "## 结论\n仅供测试的归纳。")
        self.assertEqual(result["provider"], "research_engine")
        self.assertEqual(result["tokens_in"], 12)
        self.assertEqual(forward.call_args.args, ("POST", "/api/ai/post-summaries"))
        payload = forward.call_args.kwargs["payload"]
        self.assertNotIn("api_key", payload)
        self.assertNotIn("base_url", payload)

    def test_missing_endpoint_and_invalid_source_never_become_success(self):
        for status, data in [
            (404, {}),
            (504, {}),
            (503, {}),
            (200, {"summary_source": "mock_local", "summary_md": "原文"}),
            (200, {"summary_source": "llm", "summary_md": " "}),
        ]:
            with self.subTest(status=status, data=data):
                with self.assertRaises(AiError) as error:
                    self.invoke(status, data)
                self.assertNotIn("ResearchEngine", str(error.exception))
                self.assertNotIn("post-summaries", str(error.exception))

    def test_payload_limits_and_truncation(self):
        request = TaskRequest(
            variables={
                "title": "t" * 600,
                "body": "b" * 21000,
                "code_snippet": "c" * 21000,
                "grounding": {},
                "truncated": False,
            }
        )
        payload = re_payload(request)
        self.assertEqual(
            (len(payload["title"]), len(payload["body"]), len(payload["code_snippet"])),
            (512, 20000, 20000),
        )


class SummaryContractTest(unittest.TestCase):
    def test_validator_rejects_empty_or_non_json(self):
        request = TaskRequest(variables={})
        for raw in ["", "not json", '{"summary_md":" "}', '{"other":1}']:
            with self.subTest(raw=raw):
                with self.assertRaises(AiBadOutput):
                    validate_summary(raw, request)

    def test_validator_accepts_fenced_json(self):
        out = validate_summary('```json\n{"summary_md":"要点"}\n```', TaskRequest(variables={}))
        self.assertEqual(out["summary_md"], "要点")

    def test_parse_re_summary_maps_model_fields(self):
        out = parse_re_summary(dict(RE_RESPONSE))
        self.assertEqual(out["provider"], "research_engine")
        self.assertEqual(out["data"]["summary_md"], "## 结论\n仅供测试的归纳。")

    def test_parse_re_summary_rejects_mock_source(self):
        with self.assertRaises(AiBadOutput):
            parse_re_summary({"summary_source": "mock_local", "summary_md": "原文"})


class SkillSummaryTest(unittest.TestCase):
    def test_explicit_local_llm_still_wins(self):
        with patch("ai.runtime.skills.available_task", return_value=True), patch(
            "ai.runtime.skills.run_task",
            return_value={
                "content": '{"summary_md":"本地模型摘要"}',
                "tokens_in": 1,
                "tokens_out": 1,
                "data": {"summary_md": "本地模型摘要"},
            },
        ) as llm:
            result = skill_summarize_post({"body": "这是用来验证模型路径的一段足够长的研究说明正文。"}, {})
        self.assertEqual(result["board_patch"]["artifacts"]["summary_source"], "llm")
        self.assertEqual(result["outputs"]["summary_md"], "本地模型摘要")
        self.assertEqual(llm.call_args.args[0], "community.summarize_post")

    def test_shared_model_result_keeps_usage_and_hides_base64(self):
        with patch("ai.runtime.skills.available_task", return_value=True), patch(
            "ai.runtime.skills.run_task",
            return_value={
                "content": "## 结论\n归纳。",
                "tokens_in": 32,
                "tokens_out": 12,
                "provider": "research_engine",
                "model": "shared",
                "data": {"summary_md": "## 结论\n归纳。"},
            },
        ) as router_call:
            result = skill_summarize_post(
                {"title": "虚构测试", "body": "<p>测试内容<img src='data:image/png;base64,FAKE'></p>"},
                {},
            )
        self.assertEqual(result["board_patch"]["artifacts"]["summary_source"], "llm")
        self.assertEqual(result["tokens_in"], 32)
        self.assertEqual(result["provider"], "research_engine")
        variables = router_call.call_args.kwargs["variables"]
        self.assertNotIn("base64", variables["body"])

    def test_only_local_environment_without_credentials_keeps_honest_excerpt(self):
        with patch("ai.runtime.skills.available_task", return_value=False):
            result = skill_summarize_post({"title": "测试", "body": "很短的内容"}, {})
        self.assertEqual(result["board_patch"]["artifacts"]["summary_source"], "mock_local")


if __name__ == "__main__":
    unittest.main()
