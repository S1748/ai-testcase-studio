from typing import Any

from app.skills.base import SkillContext, SkillMeta, SkillRunFn
from app.skills.loader import discover_skills, normalize_inputs

STRATEGY_DEFAULTS = {
    "full": {
        "title": "完整用例",
        "description": "覆盖功能、边界与异常，并自动标记其中的冒烟用例",
        "min_cases_per_feature": 5,
        "max_cases_per_feature": 12,
        "recommended": True,
    },
    "quick": {
        "title": "快速冒烟",
        "description": "只生成核心主路径冒烟用例，每个功能点 2～4 条",
        "min_cases_per_feature": 2,
        "max_cases_per_feature": 4,
        "recommended": False,
    },
}

LEGACY_SKILL_ALIASES = {
    "api": "api_test",
}

LEGACY_STRATEGY_MAP = {
    "detailed": "full",
    "standard": "full",
    "smoke": "quick",
    "functional_only": "quick",
}


class SkillRegistry:
    def __init__(self) -> None:
        self._metas, self._handlers = discover_skills()

    def reload(self) -> None:
        self._metas, self._handlers = discover_skills()

    def list_skills(
        self,
        *,
        category: str | None = None,
        stage: str | None = None,
        selectable_only: bool = False,
    ) -> list[SkillMeta]:
        items = list(self._metas.values())
        if category:
            items = [s for s in items if s.category == category]
        if stage:
            items = [s for s in items if s.stage == stage]
        if selectable_only:
            items = [s for s in items if s.ui.selectable]
        return sorted(items, key=lambda s: s.name)

    def get_skill(self, name: str) -> SkillMeta:
        resolved = self.resolve_skill_name(name)
        if resolved not in self._metas:
            raise KeyError(f"Skill 不存在: {name}")
        return self._metas[resolved]

    def resolve_skill_name(self, name: str) -> str:
        return LEGACY_SKILL_ALIASES.get(name, name)

    def list_selectable_specialists(self) -> list[SkillMeta]:
        return self.list_skills(category="specialist", selectable_only=True)

    def list_strategies(self) -> list[dict[str, Any]]:
        case_writer = self._metas.get("case_writer")
        strategies = []
        source = case_writer.strategies if case_writer else STRATEGY_DEFAULTS
        for key, spec in source.items():
            defaults = STRATEGY_DEFAULTS.get(key, {})
            merged = {**defaults, **spec, "key": key}
            strategies.append(merged)
        if not strategies:
            for key, spec in STRATEGY_DEFAULTS.items():
                strategies.append({**spec, "key": key})
        return strategies

    def normalize_strategy(self, strategy: str) -> str:
        valid = set(STRATEGY_DEFAULTS)
        case_writer = self._metas.get("case_writer")
        if case_writer:
            valid |= set(case_writer.strategies)
        if strategy in valid:
            return strategy
        return LEGACY_STRATEGY_MAP.get(strategy, "full")

    def validate_specialist_skills(self, names: list[str]) -> list[str]:
        allowed = {s.name for s in self.list_selectable_specialists()}
        result = []
        for name in names:
            resolved = self.resolve_skill_name(name)
            if resolved in allowed:
                result.append(resolved)
        return result

    async def run(self, name: str, inputs: dict[str, Any], context: SkillContext) -> dict[str, Any]:
        resolved = self.resolve_skill_name(name)
        if resolved not in self._handlers:
            raise KeyError(f"Skill 不存在: {name}")
        meta = self._metas[resolved]
        handler: SkillRunFn = self._handlers[resolved]
        normalized = normalize_inputs(meta, inputs)
        return await handler(normalized, context)


_registry: SkillRegistry | None = None


def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
