from pathlib import Path

from app.skills.base import SkillContext
from app.skills.shared.llm_runner import call_for_cases
from app.skills.shared.mock import mock_cases
from app.skills.shared.output_parser import feature_to_user_prompt
from app.skills.shared.prompt_loader import load_prompt

SKILL_DIR = Path(__file__).resolve().parent
SKILL_NAME = "api_test"


async def run(inputs: dict, context: SkillContext) -> dict:
    feature_item = inputs["feature_item"]
    scope = inputs.get("scope")
    knowledge = inputs.get("knowledge")
    if context.use_mock:
        return {"cases": mock_cases(feature_item["feature"], 2, ["exception"], SKILL_NAME)}

    prompt = load_prompt(SKILL_DIR, "prompt.md")
    cases = await call_for_cases(
        prompt,
        feature_to_user_prompt(feature_item, scope, knowledge),
        SKILL_NAME,
        context.model_config,
    )
    return {"cases": cases}
