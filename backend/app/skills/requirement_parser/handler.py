from app.services.llm import chat_completion
from app.skills.base import SkillContext
from app.skills.shared.mock import MOCK_REQUIREMENT_ITEMS
from app.skills.shared.output_parser import parse_items_response
from app.skills.shared.prompt_loader import load_prompt

SKILL_DIR = __import__("pathlib").Path(__file__).resolve().parent


async def run(inputs: dict, context: SkillContext) -> dict:
    raw_content = inputs["raw_content"]
    if context.use_mock:
        return {"items": MOCK_REQUIREMENT_ITEMS}

    system_prompt = load_prompt(SKILL_DIR, "prompt.md")
    user_prompt = f"请分析以下需求文档并提取功能点：\n\n{raw_content}"
    result = await chat_completion(system_prompt, user_prompt, context.model_config)
    return {"items": parse_items_response(result)}
