"""社区读帖摘要：响应契约与本地执行链（社区摘要已移交 SVQuant）。"""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ai.errors import AiBadOutput, AiNotConfigured
from ai.gateway import providers
from ai.router import run_task
from ai.router.specs import EXECUTOR_LOCAL, EXECUTOR_RE, TaskRequest, get_task
from ai.router.tasks.community_summary import validate_summary
from ai.runtime.skills import skill_summarize_post


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


class LocalOnlySpecTest(unittest.TestCase):
    def test_summary_no_longer_depends_on_research_service(self):
        spec = get_task("community.summarize_post")
        self.assertEqual(spec.executors, (EXECUTOR_LOCAL,))
        self.assertNotIn(EXECUTOR_RE, spec.executors)
        self.assertIsNone(spec.re_path)
        self.assertIsNone(spec.re_payload)
        self.assertIsNone(spec.re_parse)

    def test_local_unavailable_never_falls_back_to_research_service(self):
        forward = MagicMock(return_value=(200, {}, {}))
        with patch(
            "services.core.env_config.env", return_value="http://internal-re.test"
        ), patch.dict(
            sys.modules,
            {"services.core.re_http_gateway": SimpleNamespace(forward_re=forward)},
        ), patch.object(
            providers, "resolve_target", side_effect=AiNotConfigured("no key")
        ):
            with self.assertRaises(AiNotConfigured):
                run_task(
                    "community.summarize_post",
                    messages=[{"role": "user", "content": "ignored"}],
                    variables={"body": "正文"},
                )
        forward.assert_not_called()


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

    def test_model_result_keeps_usage_and_hides_base64(self):
        with patch("ai.runtime.skills.available_task", return_value=True), patch(
            "ai.runtime.skills.run_task",
            return_value={
                "content": "## 结论\n归纳。",
                "tokens_in": 32,
                "tokens_out": 12,
                "provider": "openai_compatible",
                "model": "local-model",
                "data": {"summary_md": "## 结论\n归纳。"},
            },
        ) as router_call:
            result = skill_summarize_post(
                {"title": "虚构测试", "body": "<p>测试内容<img src='data:image/png;base64,FAKE'></p>"},
                {},
            )
        self.assertEqual(result["board_patch"]["artifacts"]["summary_source"], "llm")
        self.assertEqual(result["tokens_in"], 32)
        self.assertEqual(result["provider"], "openai_compatible")
        variables = router_call.call_args.kwargs["variables"]
        self.assertNotIn("base64", variables["body"])

    def test_only_local_environment_without_credentials_keeps_honest_excerpt(self):
        with patch("ai.runtime.skills.available_task", return_value=False):
            result = skill_summarize_post({"title": "测试", "body": "很短的内容"}, {})
        self.assertEqual(result["board_patch"]["artifacts"]["summary_source"], "mock_local")


if __name__ == "__main__":
    unittest.main()
