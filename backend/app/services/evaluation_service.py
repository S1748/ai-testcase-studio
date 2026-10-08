"""离线评测：对评测样本走完整生成链路，产出五指标。

指标口径：
- success: 任务完成且产出用例
- usable_rate: Judge 综合分 >= 4 的用例占比（离线近似，线上以人工采纳率为准）
- recall: 标准测试点被生成用例覆盖的比例（LLM 批量判定，mock 模式用关键词匹配）
- duplicate_rate / hallucination_count: 来自质检报告
- tokens / duration: 成本
"""

import asyncio
import json
import time

from sqlalchemy.orm import Session, joinedload

from app.database import SessionLocal
from app.models.evaluation import EvalResult, EvalRun, EvalSample
from app.models.generation import GenerationTask
from app.models.requirement import RequirementDocument
from app.services.generation_service import confirm_requirements, run_generation, structure_requirements
from app.services.llm import chat_completion, parse_json_response
from app.services.settings_service import RuntimeModelConfig, get_project_runtime_config

USABLE_SCORE_THRESHOLD = 4.0

COVERAGE_PROMPT = """你是测试评审专家。给你一组标准测试点和一组 AI 生成的测试用例，判断每个测试点是否被至少一条用例覆盖。
覆盖的标准：有用例的标题/步骤/预期结果针对该测试点描述的场景做了验证。
只输出 JSON：{"covered_indexes": [0, 2, 5]}（被覆盖的测试点编号列表），不要解释。"""


def _parse_checkpoints(sample: EvalSample) -> list[dict]:
    try:
        data = json.loads(sample.checkpoints or "[]")
    except json.JSONDecodeError:
        return []
    result = []
    for cp in data if isinstance(data, list) else []:
        if isinstance(cp, str):
            result.append({"text": cp, "keywords": []})
        elif isinstance(cp, dict) and (cp.get("text") or "").strip():
            keywords = [str(k).strip() for k in (cp.get("keywords") or []) if str(k).strip()]
            result.append({"text": str(cp["text"]).strip(), "keywords": keywords})
    return result


def _keyword_coverage(checkpoints: list[dict], corpus: str) -> set[int]:
    covered = set()
    for idx, cp in enumerate(checkpoints):
        keywords = cp["keywords"] or [cp["text"]]
        if any(k and k in corpus for k in keywords):
            covered.add(idx)
    return covered


async def _compute_recall(
    checkpoints: list[dict],
    drafts: list,
    model_config: RuntimeModelConfig,
) -> tuple[float | None, list[str]]:
    """返回 (召回率, 未覆盖的测试点文本列表)。"""
    if not checkpoints:
        return None, []
    corpus = "\n".join(f"{d.title} {d.steps} {d.expected_result}" for d in drafts)

    if model_config.use_mock_llm:
        covered = _keyword_coverage(checkpoints, corpus)
    else:
        cp_lines = [f"{i}. {cp['text']}" for i, cp in enumerate(checkpoints)]
        case_lines = [
            json.dumps(
                {"title": d.title, "steps": d.steps, "expected_result": d.expected_result},
                ensure_ascii=False,
            )
            for d in drafts
        ]
        user_prompt = "标准测试点：\n" + "\n".join(cp_lines) + "\n\n生成用例：\n" + "\n".join(case_lines)
        try:
            text = await chat_completion(
                COVERAGE_PROMPT,
                user_prompt,
                model_config,
                use_eval_model=True,
            )
            data = parse_json_response(text)
            indexes = data.get("covered_indexes", []) if isinstance(data, dict) else []
            covered = {i for i in indexes if isinstance(i, int) and 0 <= i < len(checkpoints)}
        except Exception:
            covered = _keyword_coverage(checkpoints, corpus)

    uncovered = [cp["text"] for i, cp in enumerate(checkpoints) if i not in covered]
    return round(len(covered) / len(checkpoints) * 100, 1), uncovered


async def _watch_task_progress(
    run_id: int, task_id: int, base_pct: float, slice_pct: float, stop: asyncio.Event
) -> None:
    """生成期间每 2 秒把生成任务的进度映射到评测运行的进度条上。

    用独立 Session 读写，避免与主流程的 Session 交叉；事件循环单线程，
    同步 DB 操作不会与主流程真正并发。
    """
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=2.0)
            break
        except asyncio.TimeoutError:
            pass
        wdb = SessionLocal()
        try:
            task = wdb.query(GenerationTask).get(task_id)
            run = wdb.query(EvalRun).get(run_id)
            if task and run and run.status == "running":
                run.progress = min(99, int(base_pct + slice_pct * task.progress / 100))
                if task.stage:
                    run.stage = task.stage
                wdb.commit()
        except Exception:
            pass
        finally:
            wdb.close()


async def _eval_one_sample(
    db: Session, run: EvalRun, sample: EvalSample, strategy: str,
    model_config: RuntimeModelConfig,
    base_pct: float = 0.0, slice_pct: float = 100.0,
) -> dict:
    started = time.monotonic()

    run.stage = "结构化需求"
    db.commit()

    doc = RequirementDocument(
        project_id=run.project_id,
        title=f"[评测] {sample.title}",
        source_type="eval",
        raw_content=sample.content,
        is_eval=True,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    await structure_requirements(db, doc)
    confirm_requirements(db, doc.id)

    task = GenerationTask(
        project_id=run.project_id,
        document_id=doc.id,
        strategy=strategy,
        strategy_config=json.dumps({"strategy": strategy, "specialist_skills": []}),
        status="pending",
        is_eval=True,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    stop = asyncio.Event()
    watcher = asyncio.create_task(_watch_task_progress(run.id, task.id, base_pct, slice_pct, stop))
    try:
        await run_generation(db, task)
    except Exception:
        pass  # 失败信息已写入 task.error_message，计入成功率分母
    finally:
        stop.set()
        await watcher
    db.refresh(task)

    drafts = list(task.drafts or [])
    report = task.quality_report
    total = len(drafts)
    success = task.status == "completed" and total > 0

    usable = sum(1 for d in drafts if (d.judge_score or 0) >= USABLE_SCORE_THRESHOLD)
    checkpoints = _parse_checkpoints(sample)
    run.stage = "召回率判定"
    db.commit()
    if success:
        recall, uncovered_checkpoints = await _compute_recall(checkpoints, drafts, model_config)
    elif checkpoints:
        recall, uncovered_checkpoints = 0.0, [cp["text"] for cp in checkpoints]
    else:
        recall, uncovered_checkpoints = None, []

    return {
        "task_id": task.id,
        "success": success,
        "error": task.error_message or "",
        "total_cases": total,
        "usable_cases": usable,
        "usable_rate": round(usable / total * 100, 1) if total else 0.0,
        "recall": recall,
        "checkpoint_count": len(checkpoints),
        "uncovered_checkpoints": uncovered_checkpoints,
        "avg_judge_score": report.avg_judge_score if report else None,
        "hallucination_count": report.hallucination_count if report else 0,
        "duplicate_count": report.duplicate_count if report else 0,
        "duplicate_rate": round((report.duplicate_count if report else 0) / total * 100, 1) if total else 0.0,
        "tokens": task.tokens_used or 0,
        "duration_sec": round(time.monotonic() - started, 1),
    }


def _aggregate(sample_metrics: list[dict]) -> dict:
    total_samples = len(sample_metrics)
    success_count = sum(1 for m in sample_metrics if m["success"])
    total_cases = sum(m["total_cases"] for m in sample_metrics)
    usable_cases = sum(m["usable_cases"] for m in sample_metrics)
    duplicate_count = sum(m["duplicate_count"] for m in sample_metrics)
    recalls = [m["recall"] for m in sample_metrics if m["recall"] is not None]
    judge_scores = [m["avg_judge_score"] for m in sample_metrics if m["avg_judge_score"] is not None]

    def rate(part, whole):
        return round(part / whole * 100, 1) if whole else 0.0

    return {
        "sample_count": total_samples,
        "success_rate": rate(success_count, total_samples),
        "total_cases": total_cases,
        "usable_rate": rate(usable_cases, total_cases),
        "recall": round(sum(recalls) / len(recalls), 1) if recalls else None,
        "duplicate_rate": rate(duplicate_count, total_cases),
        "hallucination_count": sum(m["hallucination_count"] for m in sample_metrics),
        "avg_judge_score": round(sum(judge_scores) / len(judge_scores), 2) if judge_scores else None,
        "total_tokens": sum(m["tokens"] for m in sample_metrics),
        "total_duration_sec": round(sum(m["duration_sec"] for m in sample_metrics), 1),
    }


async def run_evaluation(db: Session, run_id: int) -> None:
    run = db.query(EvalRun).options(joinedload(EvalRun.results)).get(run_id)
    if not run:
        return
    model_config = get_project_runtime_config(db, run.project_id)

    run.status = "running"
    run.progress = 0
    db.commit()

    try:
        results = (
            db.query(EvalResult)
            .options(joinedload(EvalResult.sample))
            .filter(EvalResult.run_id == run.id)
            .all()
        )
        config = json.loads(run.config or "{}")
        strategy = config.get("strategy", "full")

        sample_metrics = []
        total = len(results)
        for idx, result in enumerate(results):
            result.status = "running"
            run.progress = int(idx / total * 100)
            db.commit()

            metrics = await _eval_one_sample(
                db, run, result.sample, strategy, model_config,
                base_pct=idx / total * 100, slice_pct=100 / total,
            )
            result.task_id = metrics["task_id"]
            result.status = "completed" if metrics["success"] else "failed"
            result.metrics = json.dumps(metrics, ensure_ascii=False)
            sample_metrics.append(metrics)
            run.progress = int((idx + 1) / total * 100)
            db.commit()

        run.metrics = json.dumps(_aggregate(sample_metrics), ensure_ascii=False)
        run.status = "completed"
        run.progress = 100
        run.stage = ""
        db.commit()
    except Exception as e:
        run.status = "failed"
        run.error_message = str(e)
        run.stage = ""
        for result in run.results:
            if result.status == "running":
                result.status = "failed"
        db.commit()
        raise
