"""全局评测 API：评测衡量的是生成能力（Prompt / 模型 / RAG 策略），与具体业务项目无关。

所有样本与运行挂在一个自动创建的隐藏评测项目下（Project.is_eval=True），
生成链路无需改动，业务列表通过 is_eval 过滤不受影响。
"""

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.database import SessionLocal, get_db
from app.api.deps import current_user_id
from app.models.evaluation import EvalResult, EvalRun, EvalSample
from app.models.generation import GenerationTask
from app.models.project import Project
from app.schemas import (
    EvalRunCreate,
    EvalRunOut,
    EvalResultOut,
    EvalSampleCreate,
    EvalSampleOut,
    EvalSampleUpdate,
    GenerationTaskOut,
)
from app.services.evaluation_service import run_evaluation

router = APIRouter(prefix="/evaluations", tags=["evaluations"])

EVAL_PROJECT_NAME = "__evaluation__"


def _eval_project(db: Session) -> Project:
    user_id = current_user_id(db)
    project = db.query(Project).filter(Project.user_id == user_id, Project.is_eval == True).first()
    if not project:
        project = Project(
            user_id=user_id,
            name=EVAL_PROJECT_NAME,
            description="评测专用隐藏项目",
            is_eval=True,
        )
        db.add(project)
        try:
            db.commit()
        except IntegrityError:
            # 同一用户首次并发进入评测页时，由唯一索引保证只保留一个隐藏项目。
            db.rollback()
            project = db.query(Project).filter(
                Project.user_id == user_id,
                Project.is_eval == True,
            ).first()
            if not project:
                raise
        db.refresh(project)
    return project


def _sample_to_out(sample: EvalSample) -> EvalSampleOut:
    try:
        checkpoints = json.loads(sample.checkpoints or "[]")
    except json.JSONDecodeError:
        checkpoints = []
    return EvalSampleOut(
        id=sample.id,
        project_id=sample.project_id,
        title=sample.title,
        content=sample.content,
        checkpoints=checkpoints,
        created_at=sample.created_at,
    )


def _parse_json(raw: str, fallback):
    try:
        data = json.loads(raw or "")
        return data if isinstance(data, type(fallback)) else fallback
    except json.JSONDecodeError:
        return fallback


def _run_to_out(run: EvalRun, sample_titles: dict[int, str]) -> EvalRunOut:
    return EvalRunOut(
        id=run.id,
        project_id=run.project_id,
        label=run.label,
        config=_parse_json(run.config, {}),
        status=run.status,
        progress=run.progress,
        stage=run.stage or "",
        error_message=run.error_message,
        metrics=_parse_json(run.metrics, {}),
        created_at=run.created_at,
        results=[
            EvalResultOut(
                id=r.id,
                sample_id=r.sample_id,
                sample_title=sample_titles.get(r.sample_id, ""),
                task_id=r.task_id,
                status=r.status,
                metrics=_parse_json(r.metrics, {}),
            )
            for r in run.results
        ],
    )


def _sample_titles(db: Session, project_id: int) -> dict[int, str]:
    return dict(
        db.query(EvalSample.id, EvalSample.title)
        .filter(EvalSample.project_id == project_id)
        .all()
    )


# ---------- 样本管理 ----------

@router.get("/samples", response_model=list[EvalSampleOut])
def list_samples(db: Session = Depends(get_db)):
    project_id = _eval_project(db).id
    samples = (
        db.query(EvalSample)
        .filter(EvalSample.project_id == project_id)
        .order_by(EvalSample.created_at.desc())
        .all()
    )
    return [_sample_to_out(s) for s in samples]


@router.post("/samples", response_model=EvalSampleOut, status_code=201)
def create_sample(data: EvalSampleCreate, db: Session = Depends(get_db)):
    if not data.title.strip() or not data.content.strip():
        raise HTTPException(400, "标题和需求内容不能为空")

    sample = EvalSample(
        project_id=_eval_project(db).id,
        title=data.title.strip(),
        content=data.content,
        checkpoints=json.dumps([cp.model_dump() for cp in data.checkpoints], ensure_ascii=False),
    )
    db.add(sample)
    db.commit()
    db.refresh(sample)
    return _sample_to_out(sample)


@router.put("/samples/{sample_id}", response_model=EvalSampleOut)
def update_sample(sample_id: int, data: EvalSampleUpdate, db: Session = Depends(get_db)):
    project_id = _eval_project(db).id
    sample = db.query(EvalSample).filter(
        EvalSample.id == sample_id,
        EvalSample.project_id == project_id,
    ).first()
    if not sample:
        raise HTTPException(404, "评测样本不存在")

    if data.title is not None:
        sample.title = data.title.strip()
    if data.content is not None:
        sample.content = data.content
    if data.checkpoints is not None:
        sample.checkpoints = json.dumps([cp.model_dump() for cp in data.checkpoints], ensure_ascii=False)
    db.commit()
    db.refresh(sample)
    return _sample_to_out(sample)


@router.delete("/samples/{sample_id}", status_code=204)
def delete_sample(sample_id: int, db: Session = Depends(get_db)):
    project_id = _eval_project(db).id
    sample = db.query(EvalSample).filter(
        EvalSample.id == sample_id,
        EvalSample.project_id == project_id,
    ).first()
    if not sample:
        raise HTTPException(404, "评测样本不存在")
    used = db.query(EvalResult).filter(EvalResult.sample_id == sample_id).count()
    if used:
        raise HTTPException(400, "该样本已被评测运行引用，不能删除")
    db.delete(sample)
    db.commit()


# ---------- 评测运行 ----------

async def _run_eval_background(run_id: int):
    db = SessionLocal()
    try:
        await run_evaluation(db, run_id)
    finally:
        db.close()


@router.get("/runs", response_model=list[EvalRunOut])
def list_runs(db: Session = Depends(get_db)):
    project_id = _eval_project(db).id
    runs = (
        db.query(EvalRun)
        .options(joinedload(EvalRun.results))
        .filter(EvalRun.project_id == project_id)
        .order_by(EvalRun.created_at.desc())
        .all()
    )
    titles = _sample_titles(db, project_id)
    return [_run_to_out(r, titles) for r in runs]


@router.post("/runs", response_model=EvalRunOut, status_code=201)
def create_run(
    data: EvalRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if not data.label.strip():
        raise HTTPException(400, "请填写运行标签（如 baseline）")
    project_id = _eval_project(db).id
    samples = db.query(EvalSample).filter(
        EvalSample.project_id == project_id,
        EvalSample.id.in_(data.sample_ids),
    ).all()
    if not samples:
        raise HTTPException(400, "请至少选择一个评测样本")

    running = db.query(EvalRun).filter(
        EvalRun.project_id == project_id,
        EvalRun.status.in_(["pending", "running"]),
    ).count()
    if running:
        raise HTTPException(400, "已有评测正在运行，请等待完成")

    run = EvalRun(
        project_id=project_id,
        label=data.label.strip(),
        config=json.dumps({"strategy": data.strategy}, ensure_ascii=False),
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    for sample in samples:
        db.add(EvalResult(run_id=run.id, sample_id=sample.id))
    db.commit()

    background_tasks.add_task(_run_eval_background, run.id)
    db.refresh(run)
    return _run_to_out(run, _sample_titles(db, project_id))


@router.get("/runs/{run_id}", response_model=EvalRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    project_id = _eval_project(db).id
    run = (
        db.query(EvalRun)
        .options(joinedload(EvalRun.results))
        .filter(EvalRun.id == run_id, EvalRun.project_id == project_id)
        .first()
    )
    if not run:
        raise HTTPException(404, "评测运行不存在")
    return _run_to_out(run, _sample_titles(db, project_id))


@router.get("/tasks/{task_id}", response_model=GenerationTaskOut)
def get_eval_task(task_id: int, db: Session = Depends(get_db)):
    """评测样本对应生成任务的完整明细（用例 + 评分 + 质检报告）。"""
    project_id = _eval_project(db).id
    task = (
        db.query(GenerationTask)
        .options(joinedload(GenerationTask.drafts), joinedload(GenerationTask.quality_report))
        .filter(
            GenerationTask.id == task_id,
            GenerationTask.project_id == project_id,
            GenerationTask.is_eval == True,
        )
        .first()
    )
    if not task:
        raise HTTPException(404, "评测任务不存在")
    return task


@router.delete("/runs/{run_id}", status_code=204)
def delete_run(run_id: int, db: Session = Depends(get_db)):
    project_id = _eval_project(db).id
    run = db.query(EvalRun).filter(
        EvalRun.id == run_id,
        EvalRun.project_id == project_id,
    ).first()
    if not run:
        raise HTTPException(404, "评测运行不存在")
    if run.status == "running":
        raise HTTPException(400, "评测正在运行，不能删除")
    db.delete(run)
    db.commit()
