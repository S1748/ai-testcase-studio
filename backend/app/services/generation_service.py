import json

from sqlalchemy.orm import Session

from app.models.generation import GeneratedCaseDraft, GenerationTask, QualityReport
from app.models.requirement import RequirementDocument, RequirementItem
from app.models.testcase import TestCase
from app.services.knowledge_service import retrieve
from app.services.llm import start_token_tracking, total_tokens
from app.services.settings_service import RuntimeModelConfig, get_project_runtime_config
from app.services.quality_checker import (
    build_quality_report,
    check_case,
    detect_duplicates,
    is_meaningful_case,
    normalize_steps,
)
from app.skills import parse_requirements
from app.skills.base import SkillContext
from app.skills.registry import get_registry


def normalize_strategy(strategy: str) -> str:
    return get_registry().normalize_strategy(strategy)


def parse_strategy_config(task: GenerationTask) -> dict:
    registry = get_registry()
    if not task.strategy_config:
        return {
            "strategy": registry.normalize_strategy(task.strategy),
            "specialist_skills": [],
            "use_knowledge": False,
        }
    try:
        data = json.loads(task.strategy_config)
        if isinstance(data, dict):
            preset = data.get("strategy") or data.get("preset") or task.strategy
            skills = data.get("specialist_skills") or []
            return {
                "strategy": registry.normalize_strategy(preset),
                "specialist_skills": registry.validate_specialist_skills(skills),
                "use_knowledge": bool(data.get("use_knowledge", False)),
            }
    except json.JSONDecodeError:
        pass
    return {
        "strategy": registry.normalize_strategy(task.strategy),
        "specialist_skills": [],
        "use_knowledge": False,
    }


def build_strategy_config_payload(data) -> str:
    registry = get_registry()
    specialist_skills = registry.validate_specialist_skills(data.specialist_skills or [])
    return json.dumps(
        {
            "strategy": registry.normalize_strategy(data.strategy),
            "specialist_skills": specialist_skills,
            "use_knowledge": bool(getattr(data, "use_knowledge", False)),
        },
        ensure_ascii=False,
    )


def _skill_context(
    task: GenerationTask,
    strategy: str,
    model_config: RuntimeModelConfig,
) -> SkillContext:
    return SkillContext(
        model_config=model_config,
        project_id=task.project_id,
        task_id=task.id,
        strategy=strategy,
        use_mock=model_config.use_mock_llm,
    )


async def structure_requirements(db: Session, document: RequirementDocument) -> list[RequirementItem]:
    model_config = get_project_runtime_config(db, document.project_id)
    items_data = await parse_requirements(document.raw_content, model_config)
    document.status = "structured"
    db.query(RequirementItem).filter(RequirementItem.document_id == document.id).delete()

    db_items = []
    for idx, item in enumerate(items_data):
        db_item = RequirementItem(
            document_id=document.id,
            module=item.get("module", ""),
            feature=item.get("feature", ""),
            description=item.get("description", ""),
            acceptance_criteria=item.get("acceptance_criteria", ""),
            constraints=item.get("constraints", ""),
            priority=item.get("priority", "P1"),
            sort_order=idx,
            confirmed=False,
        )
        db.add(db_item)
        db_items.append(db_item)

    db.commit()
    for item in db_items:
        db.refresh(item)
    return db_items


def confirm_requirements(db: Session, document_id: int, item_ids: list[int] | None = None):
    if item_ids is not None:
        db.query(RequirementItem).filter(
            RequirementItem.document_id == document_id,
            RequirementItem.id.in_(item_ids),
        ).update({"confirmed": True}, synchronize_session=False)
        db.query(RequirementItem).filter(
            RequirementItem.document_id == document_id,
            ~RequirementItem.id.in_(item_ids),
        ).update({"confirmed": False}, synchronize_session=False)
    else:
        db.query(RequirementItem).filter(RequirementItem.document_id == document_id).update(
            {"confirmed": True}, synchronize_session=False
        )

    doc = db.get(RequirementDocument, document_id)
    doc.status = "confirmed"
    db.commit()


def _parse_scope(raw: str) -> dict | None:
    """把 RequirementDocument.test_scope 的 JSON 字符串解析为 dict，无效返回 None。"""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    normalized = {
        "in_scope": [str(s).strip() for s in (data.get("in_scope") or []) if str(s).strip()],
        "out_scope": [str(s).strip() for s in (data.get("out_scope") or []) if str(s).strip()],
        "risks": [str(s).strip() for s in (data.get("risks") or []) if str(s).strip()],
    }
    if not any(normalized.values()):
        return None
    return normalized


def _item_feature_data(item: RequirementItem) -> dict:
    return {
        "module": item.module,
        "feature": item.feature,
        "description": item.description,
        "acceptance_criteria": item.acceptance_criteria,
        "constraints": item.constraints,
        "priority": item.priority,
    }


def _draft_for_judge(draft: GeneratedCaseDraft) -> dict:
    return {
        "title": draft.title,
        "precondition": draft.precondition,
        "steps": draft.steps,
        "expected_result": draft.expected_result,
    }


async def run_judge_for_task(
    db: Session,
    task: GenerationTask,
    model_config: RuntimeModelConfig | None = None,
) -> None:
    """对任务下全部草稿按功能点批量运行 AI Judge，评分写回草稿。

    单个功能点评分失败不中断整体流程（对应草稿保持未评状态）。
    """
    registry = get_registry()
    model_config = model_config or get_project_runtime_config(db, task.project_id)
    context = _skill_context(task, "full", model_config)

    drafts = (
        db.query(GeneratedCaseDraft)
        .filter(GeneratedCaseDraft.task_id == task.id)
        .order_by(GeneratedCaseDraft.id)
        .all()
    )
    if not drafts:
        return

    item_ids = {d.requirement_item_id for d in drafts if d.requirement_item_id}
    items_map = {
        item.id: item
        for item in db.query(RequirementItem).filter(RequirementItem.id.in_(item_ids)).all()
    } if item_ids else {}

    grouped: dict[int | None, list[GeneratedCaseDraft]] = {}
    for d in drafts:
        grouped.setdefault(d.requirement_item_id, []).append(d)

    group_count = len(grouped)
    for group_idx, (item_id, group) in enumerate(grouped.items()):
        item = items_map.get(item_id)
        feature_data = _item_feature_data(item) if item else {"feature": "未知功能点"}
        # 仅在生成流程中更新进度/阶段；手动重评（任务已完成）不动进度
        if task.status == "generating":
            task.stage = f"AI 评分 {group_idx + 1}/{group_count}：{feature_data.get('feature', '')}"
            task.progress = 85 + int(10 * group_idx / group_count)
            db.commit()
        try:
            result = await registry.run(
                "case_judge",
                {"feature_item": feature_data, "cases": [_draft_for_judge(d) for d in group]},
                context,
            )
        except Exception:
            continue

        for judgement in result.get("judgements") or []:
            idx = judgement.get("index")
            if not isinstance(idx, int) or not (0 <= idx < len(group)):
                continue
            draft = group[idx]
            draft.judge_score = judgement.get("overall")
            draft.judge_issues = json.dumps(
                {
                    "relevance": judgement.get("relevance"),
                    "executability": judgement.get("executability"),
                    "verifiability": judgement.get("verifiability"),
                    "hallucination": judgement.get("hallucination", False),
                    "hallucination_reason": judgement.get("hallucination_reason", ""),
                    "comment": judgement.get("comment", ""),
                },
                ensure_ascii=False,
            )
    db.commit()


async def run_generation(db: Session, task: GenerationTask):
    registry = get_registry()
    model_config = get_project_runtime_config(db, task.project_id)
    task.status = "generating"
    task.progress = 0
    task.stage = "准备中"
    db.commit()
    token_counter = start_token_tracking()

    try:
        items = (
            db.query(RequirementItem)
            .filter(RequirementItem.document_id == task.document_id, RequirementItem.confirmed == True)
            .order_by(RequirementItem.sort_order)
            .all()
        )
        if not items:
            task.status = "failed"
            task.error_message = "没有已确认的功能点"
            task.stage = ""
            db.commit()
            return

        document = db.get(RequirementDocument, task.document_id)
        scope = _parse_scope(document.test_scope) if document else None

        config = parse_strategy_config(task)
        strategy = config["strategy"]
        specialist_skills = config["specialist_skills"]
        use_knowledge = config["use_knowledge"]
        context = _skill_context(task, strategy, model_config)
        db.query(GeneratedCaseDraft).filter(GeneratedCaseDraft.task_id == task.id).delete()

        item_case_map: dict[int, list] = {}
        knowledge_refs: dict[int, list] = {}
        total = len(items)

        for idx, item in enumerate(items):
            feature_data = _item_feature_data(item)
            task.stage = f"生成用例 {idx + 1}/{total}：{item.feature}"
            db.commit()

            knowledge = []
            if use_knowledge:
                try:
                    query = " ".join(filter(None, [item.module, item.feature, item.description]))
                    knowledge = await retrieve(db, task.project_id, query, model_config=model_config)
                except Exception:
                    knowledge = []  # 检索失败不阻塞生成，按无知识继续
                if knowledge:
                    knowledge_refs[item.id] = [
                        {"title": k["title"], "heading": k["heading"], "score": k["score"]}
                        for k in knowledge
                    ]

            core_result = await registry.run(
                "case_writer",
                {"feature_item": feature_data, "strategy": strategy, "scope": scope, "knowledge": knowledge},
                context,
            )
            cases = list(core_result.get("cases") or [])

            for skill_name in specialist_skills:
                extra = await registry.run(
                    skill_name,
                    {"feature_item": feature_data, "scope": scope, "knowledge": knowledge},
                    context,
                )
                cases.extend(extra.get("cases") or [])

            item_case_map[item.id] = []

            for case in cases:
                if not isinstance(case, dict):
                    continue
                steps_text, steps_list = normalize_steps(case)
                if not is_meaningful_case(case, steps_list):
                    continue

                quality_status, quality_issues = check_case({**case, "steps": steps_list})

                is_smoke = bool(case.get("is_smoke", False))

                draft = GeneratedCaseDraft(
                    task_id=task.id,
                    requirement_item_id=item.id,
                    title=(case.get("title") or "").strip(),
                    priority=case.get("priority", "P2"),
                    case_type=case.get("case_type", "functional"),
                    is_smoke=is_smoke,
                    precondition=(case.get("precondition") or "").strip(),
                    steps=steps_text,
                    expected_result=(case.get("expected_result") or "").strip(),
                    quality_status=quality_status,
                    quality_issues=json.dumps(quality_issues, ensure_ascii=False),
                    skill_name=case.get("skill_name", ""),
                )
                db.add(draft)
                item_case_map[item.id].append(draft)

            task.progress = int((idx + 1) / total * 80)
            db.commit()

        drafts = db.query(GeneratedCaseDraft).filter(GeneratedCaseDraft.task_id == task.id).all()

        task.stage = "重复检测"
        duplicate_count = detect_duplicates(drafts)
        task.progress = 85
        db.commit()

        await run_judge_for_task(db, task, model_config)
        task.stage = "生成质检报告"
        task.progress = 95
        db.commit()

        report_data = build_quality_report(drafts, items, item_case_map, duplicate_count)

        existing = db.query(QualityReport).filter(QualityReport.task_id == task.id).first()
        if existing:
            db.delete(existing)

        report = QualityReport(task_id=task.id, **report_data)
        db.add(report)

        task.knowledge_refs = json.dumps(knowledge_refs, ensure_ascii=False) if knowledge_refs else ""
        task.tokens_used = total_tokens(token_counter)
        task.status = "completed"
        task.progress = 100
        task.stage = ""
        db.commit()

    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        task.tokens_used = total_tokens(token_counter)
        task.stage = ""
        db.commit()
        raise


def adopt_drafts(db: Session, task_id: int, draft_ids: list[int]) -> list[TestCase]:
    task = db.query(GenerationTask).get(task_id)
    adopted = []

    for draft_id in draft_ids:
        draft = db.query(GeneratedCaseDraft).filter(
            GeneratedCaseDraft.id == draft_id,
            GeneratedCaseDraft.task_id == task_id,
        ).first()
        if not draft:
            continue

        tc = TestCase(
            project_id=task.project_id,
            draft_id=draft.id,
            requirement_item_id=draft.requirement_item_id,
            title=draft.title,
            priority=draft.priority,
            case_type=draft.case_type,
            is_smoke=draft.is_smoke,
            precondition=draft.precondition,
            steps=draft.steps,
            expected_result=draft.expected_result,
            source="ai_generated",
        )
        db.add(tc)
        draft.review_status = "adopted"
        adopted.append(tc)

    db.commit()
    for tc in adopted:
        db.refresh(tc)
    return adopted


def reject_drafts(db: Session, task_id: int, draft_ids: list[int], reject_reason: str = ""):
    db.query(GeneratedCaseDraft).filter(
        GeneratedCaseDraft.task_id == task_id,
        GeneratedCaseDraft.id.in_(draft_ids),
    ).update({"review_status": "rejected", "reject_reason": reject_reason[:200]})
    db.commit()
