from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EvalSample(Base):
    """离线评测样本：固化的需求内容 + 人工整理的标准测试点。"""

    __tablename__ = "eval_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")  # 需求内容快照，保证每次运行输入一致
    checkpoints: Mapped[str] = mapped_column(Text, default="[]")  # JSON: [{text, keywords[]}]
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    results: Mapped[list["EvalResult"]] = relationship(back_populates="sample")


class EvalRun(Base):
    """一次评测运行：对若干样本走完整生成链路并汇总指标。"""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)  # 如 baseline-no-rag
    config: Mapped[str] = mapped_column(Text, default="{}")  # JSON: strategy / model 快照
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/completed/failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(100), default="")  # 当前阶段提示
    error_message: Mapped[str] = mapped_column(Text, default="")
    metrics: Mapped[str] = mapped_column(Text, default="{}")  # JSON: 运行级汇总指标
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    results: Mapped[list["EvalResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class EvalResult(Base):
    """单个样本在一次运行中的结果。"""

    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("eval_runs.id"), nullable=False)
    sample_id: Mapped[int] = mapped_column(ForeignKey("eval_samples.id"), nullable=False)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 关联的生成任务（可追溯）
    status: Mapped[str] = mapped_column(String(20), default="pending")
    metrics: Mapped[str] = mapped_column(Text, default="{}")  # JSON: 样本级指标
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    run: Mapped["EvalRun"] = relationship(back_populates="results")
    sample: Mapped["EvalSample"] = relationship(back_populates="results")
