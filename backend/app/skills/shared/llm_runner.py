from app.services.llm import chat_completion
from app.services.settings_service import RuntimeModelConfig
from app.skills.shared.output_parser import parse_cases_response


async def call_for_cases(
    system_prompt: str,
    user_prompt: str,
    skill_name: str,
    model_config: RuntimeModelConfig,
) -> list[dict]:
    result = await chat_completion(system_prompt, user_prompt, model_config)
    cases = parse_cases_response(result)
    for case in cases:
        case["skill_name"] = skill_name
    return cases
