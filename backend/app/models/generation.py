from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GenerationTask(Base):
    __tablename__ = "generation_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    document_id: Mapped[int] = mapped_column(ForeignKey("requirement_documents.id"), nullable=False)
    strategy: Mapped[str] = mapped_column(String(50), default="detailed")  # smoke, detailed
    strategy_config: Mapped[str] = mapped_column(Text, default="")  # JSON: strategy, specialist_skills
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending → structuring → confirmed → generating → reviewing → completed / failed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage: Mapped[str] = mapped_column(String(100), default="")  # 当前阶段提示，如「生成用例 2/5：xxx」
    error_message: Mapped[str] = mapped_column(Text, default="")
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    is_eval: Mapped[bool] = mapped_column(default=False)  # 评测运行产生的任务，业务列表默认过滤
    knowledge_refs: Mapped[str] = mapped_column(Text, default="")  # JSON: {item_id: [{title, heading, score}]}，RAG 溯源
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship(back_populates="generation_tasks")
    drafts: Mapped[list["GeneratedCaseDraft"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    quality_report: Mapped["QualityReport | None"] = relationship(
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
    )

    @property
    def review_stats(self) -> dict:
        """从 drafts 实时汇总评审信号：采纳率 / 编辑率 / 驳回率。"""
        drafts = self.drafts or []
        total = len(drafts)
        adopted = sum(1 for d in drafts if d.review_status == "adopted")
        rejected = sum(1 for d in drafts if d.review_status == "rejected")
        edited_adopted = sum(1 for d in drafts if d.review_status == "adopted" and d.was_edited)
        reviewed = adopted + rejected

        def rate(part: int, whole: int) -> float:
            return round(part / whole * 100, 1) if whole else 0.0

        return {
            "total": total,
            "adopted": adopted,
            "rejected": rejected,
            "edited_adopted": edited_adopted,
            "pending": total - reviewed,
            "reviewed": reviewed > 0,
            "adoption_rate": rate(adopted, total),
            "edit_rate": rate(edited_adopted, adopted),
            "rejection_rate": rate(rejected, total),
        }


class GeneratedCaseDraft(Base):
    __tablename__ = "generated_case_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("generation_tasks.id"), nullable=False)
    requirement_item_id: Mapped[int | None] = mapped_column(ForeignKey("requirement_items.id"))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="P2")
    case_type: Mapped[str] = mapped_column(String(20), default="functional")
    precondition: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[str] = mapped_column(Text, default="")  # JSON array as text
    expected_result: Mapped[str] = mapped_column(Text, default="")
    quality_status: Mapped[str] = mapped_column(String(20), default="pending")  # pass, warning, fail
    quality_issues: Mapped[str] = mapped_column(Text, default="")  # JSON array as text
    review_status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, to_confirm, adopted, rejected, edited
    was_edited: Mapped[bool] = mapped_column(default=False)  # 是否被人工编辑过（采纳后 review_status 会覆盖 edited，用此字段保留信号）
    reject_reason: Mapped[str] = mapped_column(String(200), default="")
    is_smoke: Mapped[bool] = mapped_column(default=False)
    skill_name: Mapped[str] = mapped_column(String(50), default="")
    judge_score: Mapped[float | None] = mapped_column(Float, nullable=True)  # AI Judge 综合分 1~5，None 表示未评
    judge_issues: Mapped[str] = mapped_column(Text, default="")  # JSON: 各维度分、幻觉标记与理由

    task: Mapped["GenerationTask"] = relationship(back_populates="drafts")
    requirement_item: Mapped["RequirementItem | None"] = relationship()

    @property
    def module(self) -> str:
        return self.requirement_item.module if self.requirement_item else ""

    @property
    def feature(self) -> str:
        return self.requirement_item.feature if self.requirement_item else ""


class QualityReport(Base):
    __tablename__ = "quality_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("generation_tasks.id"), unique=True, nullable=False)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    pass_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    coverage_rate: Mapped[float] = mapped_column(Float, default=0.0)
    uncovered_features: Mapped[str] = mapped_column(Text, default="")  # JSON array
    suggestions: Mapped[str] = mapped_column(Text, default="")
    avg_judge_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hallucination_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    task: Mapped["GenerationTask"] = relationship(back_populates="quality_report")
