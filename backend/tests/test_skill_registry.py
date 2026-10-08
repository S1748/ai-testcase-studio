"""Skill 注册表测试。

全部在 mock 模式下运行：不调用任何外部 LLM / Embedding 服务，
结果确定、可离线执行，所以能直接放进 CI。
"""
import asyncio
import unittest

from app.services.settings_service import RuntimeModelConfig
from app.skills.base import SkillContext
from app.skills.registry import get_registry


def run_async(coro):
    """在同步的 unittest 用例里驱动协程。"""
    return asyncio.run(coro)


def mock_context(strategy: str = "full") -> SkillContext:
    """构造一个不依赖真实模型的执行上下文。"""
    return SkillContext(model_config=RuntimeModelConfig(), use_mock=True, strategy=strategy)


class SkillRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = get_registry()

    # ---------- 技能发现 ----------

    def test_discovers_core_and_specialist_skills(self):
        names = {s.name for s in self.registry.list_skills()}
        self.assertIn("requirement_parser", names)
        self.assertIn("case_writer", names)
        self.assertIn("security", names)
        self.assertIn("api_test", names)

    def test_list_selectable_specialists(self):
        names = [s.name for s in self.registry.list_selectable_specialists()]
        self.assertEqual(names, ["api_test", "security"])

    def test_legacy_api_alias(self):
        self.assertEqual(self.registry.resolve_skill_name("api"), "api_test")
        validated = self.registry.validate_specialist_skills(["api", "security"])
        self.assertEqual(validated, ["api_test", "security"])

    def test_validate_specialist_skills_drops_unknown_names(self):
        self.assertEqual(self.registry.validate_specialist_skills(["not_exist"]), [])

    # ---------- 策略 ----------

    def test_list_strategies_from_manifest(self):
        keys = [s["key"] for s in self.registry.list_strategies()]
        self.assertEqual(keys, ["full", "quick"])

    def test_manifest_strategy_is_merged_with_defaults(self):
        strategies = {s["key"]: s for s in self.registry.list_strategies()}
        self.assertEqual(strategies["full"]["title"], "完整用例")
        self.assertTrue(strategies["full"]["recommended"])
        self.assertFalse(strategies["quick"]["recommended"])
        # 取值范围来自 case_writer/skill.yaml
        self.assertEqual(strategies["quick"]["min_cases_per_feature"], 2)
        self.assertEqual(strategies["quick"]["max_cases_per_feature"], 4)

    def test_normalize_strategy_maps_legacy_names(self):
        self.assertEqual(self.registry.normalize_strategy("smoke"), "quick")
        self.assertEqual(self.registry.normalize_strategy("detailed"), "full")
        self.assertEqual(self.registry.normalize_strategy("standard"), "full")
        self.assertEqual(self.registry.normalize_strategy("functional_only"), "quick")

    def test_normalize_strategy_keeps_valid_and_defaults_unknown(self):
        self.assertEqual(self.registry.normalize_strategy("quick"), "quick")
        self.assertEqual(self.registry.normalize_strategy("full"), "full")
        self.assertEqual(self.registry.normalize_strategy("whatever"), "full")

    # ---------- 执行 ----------

    def test_run_case_writer_quick_strategy_in_mock_mode(self):
        async def _run():
            return await self.registry.run(
                "case_writer",
                {"feature_item": {"feature": "登录"}, "strategy": "quick"},
                mock_context("quick"),
            )

        cases = run_async(_run())["cases"]
        # quick 策略下每个功能点 2～4 条
        self.assertGreaterEqual(len(cases), 2)
        self.assertLessEqual(len(cases), 4)
        self.assertEqual(cases[0]["skill_name"], "case_writer")
        # quick 模式生成的用例全部标记为冒烟
        self.assertTrue(all(c["is_smoke"] for c in cases))

    def test_run_case_writer_full_strategy_in_mock_mode(self):
        async def _run():
            return await self.registry.run(
                "case_writer",
                {"feature_item": {"feature": "登录"}, "strategy": "full"},
                mock_context("full"),
            )

        cases = run_async(_run())["cases"]
        self.assertEqual(len(cases), 6)
        # full 模式只有首条（P0 正常流程）算冒烟
        self.assertTrue(cases[0]["is_smoke"])
        self.assertFalse(cases[1]["is_smoke"])

    def test_run_unknown_skill_raises_key_error(self):
        async def _run():
            return await self.registry.run("not_exist", {}, mock_context())

        with self.assertRaises(KeyError):
            run_async(_run())

    # ---------- 模型配置 ----------

    def test_missing_api_key_falls_back_to_mock(self):
        """没有配置 API Key 时应自动走 mock，保证本地/CI 不依赖外部服务。"""
        self.assertTrue(RuntimeModelConfig().use_mock_llm)
        self.assertTrue(RuntimeModelConfig(llm_api_key="").use_mock_llm)
        self.assertFalse(RuntimeModelConfig(llm_api_key="sk-xxx").use_mock_llm)


if __name__ == "__main__":
    unittest.main()
