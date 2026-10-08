import asyncio
import unittest

from app.skills.base import SkillContext
from app.skills.registry import get_registry


class SkillRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = get_registry()

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

    def test_list_strategies_from_manifest(self):
        keys = [s["key"] for s in self.registry.list_strategies()]
        self.assertEqual(keys, ["smoke", "detailed"])

    def test_run_case_writer_mock(self):
        async def _run():
            ctx = SkillContext(use_mock=True, strategy="smoke")
            result = await self.registry.run(
                "case_writer",
                {"feature_item": {"feature": "登录"}, "strategy": "smoke"},
                ctx,
            )
            return result

        result = asyncio.run(_run())
        self.assertGreaterEqual(len(result["cases"]), 2)
        self.assertEqual(result["cases"][0]["skill_name"], "case_writer")


if __name__ == "__main__":
    unittest.main()
