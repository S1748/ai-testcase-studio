import json
from pathlib import Path

from app.services.llm import chat_completion, parse_json_response
from app.skills.base import SkillContext
from app.skills.shared.prompt_loader import load_prompt

SKILL_DIR = Path(__file__).resolve().parent
SKILL_NAME = "case_judge"

DIMENSIONS = ("relevance", "executability", "verifiability")


def _clamp(value, lo=1, hi=5) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return 3


def _normalize_judgement(raw: dict) -> dict:
    scores = {dim: _clamp(raw.get(dim)) for dim in DIMENSIONS}
    overall = round(sum(scores.values()) / len(scores), 1)
    return {
        "index": raw.get("index"),
        **scores,
        "overall": overall,
        "hallucination": bool(raw.get("hallucination", False)),
        "hallucination_reason": (raw.get("hallucination_reason") or "").strip(),
        "comment": (raw.get("comment") or "").strip(),
    }


def _mock_judgements(cases: list) -> list[dict]:
    result = []
    for i in range(len(cases)):
        result.append(_normalize_judgement({
            "index": i,
            "relevance": 5 - (i % 2),
            "executability": 4,
            "verifiability": 4 + (i % 2),
            "hallucination": False,
        }))
    return result


def _cases_to_prompt(feature_item: dict, cases: list[dict]) -> str:
    lines = [
        "功能点：",
        json.dumps(feature_item, ensure_ascii=False, indent=2),
        "",
        "待评分用例：",
    ]
    for idx, case in enumerate(cases):
        steps = case.get("steps")
        if isinstance(steps, str):
            try:
                steps = json.loads(steps)
            except json.JSONDecodeError:
                steps = [steps]
        lines.append(json.dumps({
            "index": idx,
            "title": case.get("title", ""),
            "precondition": case.get("precondition", ""),
            "steps": steps or [],
            "expected_result": case.get("expected_result", ""),
        }, ensure_ascii=False))
    return "\n".join(lines)


async def run(inputs: dict, context: SkillContext) -> dict:
    feature_item = inputs["feature_item"]
    cases = inputs["cases"]
    if not cases:
        return {"judgements": []}

    if context.use_mock:
        return {"judgements": _mock_judgements(cases)}

    prompt = load_prompt(SKILL_DIR, "prompt.md")
    user_prompt = _cases_to_prompt(feature_item, cases)
    # Judge 用评测专用模型，与生成模型分离，避免"自评偏置"
    text = await chat_completion(
        prompt,
        user_prompt,
        context.model_config,
        use_eval_model=True,
    )

    data = parse_json_response(text)
    raw_list = data.get("judgements", []) if isinstance(data, dict) else data
    if not isinstance(raw_list, list):
        raw_list = []

    # 按 index 对齐，缺失的条目不返回评分（保持未评状态）
    judgements = []
    seen = set()
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        item = _normalize_judgement(raw)
        idx = item["index"]
        if isinstance(idx, int) and 0 <= idx < len(cases) and idx not in seen:
            seen.add(idx)
            judgements.append(item)
    return {"judgements": judgements}
