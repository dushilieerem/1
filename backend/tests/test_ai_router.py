# -*- coding: utf-8 -*-
"""AI 路由层（ADR-037）单测：任务注册、参数取舍、执行链降级、异常语义。"""
import unittest
from unittest.mock import MagicMock, patch

from ai.errors import (
    AiBadOutput,
    AiInvalidRequest,
    AiNotConfigured,
    AiTimeout,
    AiUpstreamError,
)
from ai.gateway import providers
from ai.router import all_tasks, get_task, run_task, stream_task
from ai.router import executors as executors_module
from ai.router.specs import TaskSpec, register

# 测试专用任务：不污染真实任务表的 id 前缀
TEST_LOCAL = register(TaskSpec(task_id="test.local_only", temperature=0.15, max_tokens=77))
TEST_CHAIN = register(
    TaskSpec(
        task_id="test.chain",
        temperature=0.2,
        max_tokens=11,
        executors=("local", "re"),
        re_path="/api/ai/test",
    )
)

_OK = {
    "content": "ok",
    "message": {},
    "tool_calls": [],
    "tokens_in": 3,
    "tokens_out": 4,
    "model": "m",
    "provider": "openai_compatible",
}


class TaskRegistryTest(unittest.TestCase):
    def test_expected_tasks_are_registered(self):
        ids = {spec.task_id for spec in all_tasks()}
        for expected in (
            "assistant.chat",
            "community.polish_title",
            "community.polish_body",
            "community.suggest_section",
            "community.audit_claims",
            "community.strip_unverifiable",
            "community.summarize_post",
            "community.flag_read_risks",
            "gather_idea.factor",
            "gather_idea.gather",
            "gather_idea.idea",
            "strategy_research.agent",
        ):
            self.assertIn(expected, ids)

    def test_unknown_task_is_a_programming_error(self):
        with self.assertRaises(KeyError):
            get_task("community.not_exists")

    def test_duplicate_registration_rejected(self):
        with self.assertRaises(ValueError):
            register(TaskSpec(task_id="test.local_only"))

    def test_re_executor_requires_path(self):
        with self.assertRaises(ValueError):
            register(TaskSpec(task_id="test.bad_chain", executors=("local", "re")))

    def test_tools_only_allowed_when_declared(self):
        self.assertTrue(get_task("strategy_research.agent").allow_tools)
        self.assertFalse(get_task("community.polish_title").allow_tools)


class RunTaskTest(unittest.TestCase):
    def test_spec_params_are_used_not_caller_provided(self):
        target = providers.ChatTarget(
            provider="openai_compatible", base_url="http://x", api_key="k", model="m"
        )
        with patch.object(providers, "resolve_target", return_value=target) as resolve, patch.object(
            providers, "complete", return_value=dict(_OK)
        ) as complete:
            out = run_task("test.local_only", messages=[{"role": "user", "content": "hi"}])

        resolve.assert_called_once_with(slot="default", model=None)
        kwargs = complete.call_args.kwargs
        self.assertEqual(kwargs["temperature"], 0.15)
        self.assertEqual(kwargs["max_tokens"], 77)
        self.assertIsNone(kwargs["tools"])
        self.assertEqual(out["task"], "test.local_only")
        self.assertEqual(out["content"], "ok")
        self.assertIsInstance(out["latency_ms"], int)

    def test_temperature_override_is_honoured(self):
        target = providers.ChatTarget(
            provider="openai_compatible", base_url="http://x", api_key="k", model="m"
        )
        with patch.object(providers, "resolve_target", return_value=target), patch.object(
            providers, "complete", return_value=dict(_OK)
        ) as complete:
            run_task("test.local_only", messages=[{"role": "user", "content": "hi"}], temperature=0.9)
        self.assertEqual(complete.call_args.kwargs["temperature"], 0.9)

    def test_missing_messages_rejected_for_local_task(self):
        with self.assertRaises(AiInvalidRequest):
            run_task("test.local_only", messages=[])

    def test_unconfigured_propagates(self):
        with patch.object(
            providers, "resolve_target", side_effect=AiNotConfigured("no key")
        ):
            with self.assertRaises(AiNotConfigured):
                run_task("test.local_only", messages=[{"role": "user", "content": "hi"}])

    def test_fallback_happens_only_on_not_configured(self):
        remote = MagicMock(return_value=dict(_OK, provider="research_engine"))
        with patch.object(
            providers, "resolve_target", side_effect=AiNotConfigured("no key")
        ), patch.dict(executors_module.EXECUTORS, {"re": remote}):
            out = run_task("test.chain", messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(out["provider"], "research_engine")
        remote.assert_called_once()

    def test_upstream_error_is_not_swallowed_by_fallback(self):
        remote = MagicMock(return_value=dict(_OK))
        with patch.object(
            providers, "resolve_target", side_effect=AiUpstreamError("boom")
        ), patch.dict(executors_module.EXECUTORS, {"re": remote}):
            with self.assertRaises(AiUpstreamError):
                run_task("test.chain", messages=[{"role": "user", "content": "hi"}])
        remote.assert_not_called()

    def test_timeout_is_distinct_type(self):
        self.assertTrue(issubclass(AiTimeout, AiUpstreamError))
        self.assertEqual(AiTimeout.http_status, 504)
        self.assertEqual(AiNotConfigured.http_status, 503)
        self.assertEqual(AiBadOutput.http_status, 502)


class StreamTaskTest(unittest.TestCase):
    def test_non_stream_task_rejected(self):
        with self.assertRaises(AiInvalidRequest):
            list(stream_task("community.polish_title", messages=[{"role": "user", "content": "hi"}]))

    def test_stream_uses_assistant_slot(self):
        target = providers.ChatTarget(
            provider="ark", base_url="http://x", api_key="k", model="m", direct=True
        )
        with patch.object(providers, "resolve_target", return_value=target) as resolve, patch.object(
            providers, "stream", return_value=iter(["a", "b"])
        ):
            chunks = list(
                stream_task("assistant.chat", messages=[{"role": "user", "content": "hi"}], model="doubao-seed-2.0-pro")
            )
        self.assertEqual(chunks, ["a", "b"])
        resolve.assert_called_once_with(slot="assistant", model="doubao-seed-2.0-pro")


class ProvidersTargetTest(unittest.TestCase):
    def test_default_slot_requires_llm_key(self):
        with patch.object(providers, "env", side_effect=lambda name, default=None: None if name == "LLM_API_KEY" else default):
            with self.assertRaises(AiNotConfigured):
                providers.resolve_target(slot=providers.SLOT_DEFAULT)

    def test_code_slot_uses_ark(self):
        def fake_env(name, default=None):
            return {"ARK_API_KEY": "k", "AI_FACTOR_BASE_URL": "http://ark"}.get(name, default)

        with patch.object(providers, "env", side_effect=fake_env), patch.object(
            providers, "key_env", side_effect=lambda name: "k" if name == "ARK_API_KEY" else ""
        ):
            target = providers.resolve_target(slot=providers.SLOT_CODE)
        self.assertEqual(target.provider, "ark")
        self.assertTrue(target.direct)

    def test_code_slot_can_explicitly_use_default_gateway(self):
        def fake_env(name, default=None):
            return {
                "AI_CODE_PROVIDER": "default",
                "LLM_API_KEY": "k",
                "LLM_BASE_URL": "http://llm",
                "LLM_MODEL": "deepseek-code",
            }.get(name, default)

        with patch.object(providers, "env", side_effect=fake_env):
            target = providers.resolve_target(slot=providers.SLOT_CODE)
        self.assertEqual(target.provider, "openai_compatible")
        self.assertEqual(target.base_url, "http://llm")
        self.assertEqual(target.model, "deepseek-code")
        self.assertFalse(target.direct)

    def test_code_slot_override_without_key_fails_loudly(self):
        with patch.object(
            providers,
            "env",
            side_effect=lambda name, default=None: "default"
            if name == "AI_CODE_PROVIDER"
            else default,
        ):
            with self.assertRaises(AiNotConfigured):
                providers.resolve_target(slot=providers.SLOT_CODE)

    def test_code_slot_rejects_unknown_provider(self):
        with patch.object(
            providers,
            "env",
            side_effect=lambda name, default=None: "fake"
            if name == "AI_CODE_PROVIDER"
            else default,
        ):
            with self.assertRaises(AiNotConfigured):
                providers.resolve_target(slot=providers.SLOT_CODE)

    def test_target_repr_hides_key(self):
        target = providers.ChatTarget(
            provider="ark", base_url="http://x", api_key="SECRET", model="m"
        )
        self.assertNotIn("SECRET", repr(target))


if __name__ == "__main__":
    unittest.main()
