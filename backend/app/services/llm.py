import contextvars
import json
from typing import Any

import httpx

from app.services.model_endpoint_security import ModelEndpointError, validate_model_base_url
from app.services.settings_service import RuntimeModelConfig

# 按异步上下文累计 token 用量：run_generation 开始时创建计数器，
# 期间所有 LLM 调用（生成 + 专项 + Judge）都会累加到同一个计数器。
_token_counter: contextvars.ContextVar[dict | None] = contextvars.ContextVar("token_counter", default=None)


def start_token_tracking() -> dict:
    counter = {"prompt_tokens": 0, "completion_tokens": 0}
    _token_counter.set(counter)
    return counter


def total_tokens(counter: dict) -> int:
    return counter.get("prompt_tokens", 0) + counter.get("completion_tokens", 0)


def _record_usage(usage: dict | None) -> None:
    counter = _token_counter.get()
    if counter is None or not isinstance(usage, dict):
        return
    counter["prompt_tokens"] += usage.get("prompt_tokens", 0) or 0
    counter["completion_tokens"] += usage.get("completion_tokens", 0) or 0


def _resolve_llm(config: RuntimeModelConfig, use_eval_model: bool) -> tuple[str, str, str]:
    """返回 (base_url, api_key, model)。评测三项全部留空时整体复用生成配置。"""
    if use_eval_model:
        eval_config = (config.eval_llm_base_url, config.eval_llm_api_key, config.eval_llm_model)
        if any(eval_config):
            return eval_config
    return config.llm_base_url, config.llm_api_key, config.llm_model


class LLMCallError(RuntimeError):
    """LLM 调用失败，message 为面向用户的中文提示。"""


def _friendly_error(exc: Exception, kind: str) -> LLMCallError:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return LLMCallError(f"{kind}的 API Key 无效或已过期，请到「设置」页更新后重试")
        if code == 429:
            return LLMCallError(f"{kind}调用触发限流（429），请稍后重试")
        if code == 404:
            return LLMCallError(f"{kind}的接口地址或模型名有误（404），请检查「设置」页配置")
        return LLMCallError(f"{kind}调用失败（HTTP {code}），请检查「设置」页配置")
    return LLMCallError(f"无法连接{kind}服务，请检查接口地址与网络：{exc}")


async def chat_completion(
    system_prompt: str,
    user_prompt: str,
    config: RuntimeModelConfig,
    *,
    use_eval_model: bool = False,
) -> str:
    if config.use_mock_llm:
        return ""

    kind = "评测模型" if use_eval_model else "生成模型"
    base_url, api_key, model = _resolve_llm(config, use_eval_model)
    if not (base_url and api_key and model):
        raise LLMCallError(f"未配置{kind}，请先到「设置」页填写 API 地址、模型和 Key")
    try:
        base_url = validate_model_base_url(base_url)
    except ModelEndpointError as exc:
        raise LLMCallError(str(exc)) from exc
    try:
        async with httpx.AsyncClient(timeout=120.0, trust_env=False) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        raise _friendly_error(exc, kind) from exc
    _record_usage(data.get("usage"))
    return data["choices"][0]["message"]["content"]


async def embed_texts(texts: list[str], config: RuntimeModelConfig) -> list[list[float]]:
    """调用 OpenAI 兼容 /embeddings 接口批量向量化文本。未配置 embedding 模型时抛出异常。"""
    if not (config.embedding_base_url and config.embedding_api_key and config.embedding_model):
        raise RuntimeError("未配置 Embedding 模型，请先在设置中填写 Embedding API 地址、模型和 Key")
    base_url = validate_model_base_url(config.embedding_base_url)

    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            response = await client.post(
                f"{base_url}/embeddings",
                headers={"Authorization": f"Bearer {config.embedding_api_key}"},
                json={"model": config.embedding_model, "input": texts},
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        raise _friendly_error(exc, "Embedding 模型") from exc
    # 按 index 排序，保证返回顺序与输入一致
    items = sorted(data["data"], key=lambda d: d["index"])
    return [item["embedding"] for item in items]


async def test_model_connection(config: RuntimeModelConfig, target: str) -> dict:
    """对指定模型配置发起一次最小化调用，验证地址、模型与 Key 是否可用。

    target: generation | eval | embedding。返回 {ok, message, model, base_url}。
    """
    if target == "embedding":
        base_url = config.embedding_base_url
        api_key = config.embedding_api_key
        model = config.embedding_model
        kind = "Embedding 模型"
    else:
        use_eval = target == "eval"
        kind = "评测模型" if use_eval else "生成模型"
        if use_eval and not any(
            (config.eval_llm_base_url, config.eval_llm_api_key, config.eval_llm_model)
        ):
            return {
                "ok": True,
                "message": "评测模型未单独配置，将复用生成模型",
                "model": config.llm_model,
                "base_url": config.llm_base_url,
            }
        base_url, api_key, model = _resolve_llm(config, use_eval)

    if target == "generation" and config.use_mock_llm:
        return {
            "ok": True,
            "message": "当前为 Mock 模式，生成不会调用真实接口",
            "model": model or "",
            "base_url": base_url or "",
        }

    if not (base_url and api_key and model):
        return {
            "ok": False,
            "message": f"{kind}的 API 地址、模型和 Key 尚未配置完整",
            "model": model or "",
            "base_url": base_url or "",
        }

    try:
        base_url = validate_model_base_url(base_url)
    except ModelEndpointError as exc:
        return {"ok": False, "message": str(exc), "model": model, "base_url": base_url}

    if target == "embedding":
        path = "/embeddings"
        payload: dict = {"model": model, "input": ["连通性测试"]}
    else:
        path = "/chat/completions"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 4,
            "temperature": 0,
        }

    try:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}{path}",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as exc:
        return {
            "ok": False,
            "message": str(_friendly_error(exc, kind)),
            "model": model,
            "base_url": base_url,
        }

    return {"ok": True, "message": "连接成功", "model": model, "base_url": base_url}


def parse_json_response(text: str) -> Any:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return json.loads(text)
