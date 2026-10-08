from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db(request: Request):
    db = SessionLocal()
    auth_session = getattr(request.state, "auth_session", None)
    if auth_session:
        db.info["user_id"] = auth_session.user_id
        db.info["username"] = auth_session.username
        db.info["is_admin"] = auth_session.is_admin
    try:
        yield db
    finally:
        db.close()


def init_db():
    from app.models import evaluation, execution, generation, knowledge, project, requirement, system_config, testcase, user  # noqa: F401
    from app.models.user import User
    from app.services.auth_service import ensure_bootstrap_admin
    from app.services.settings_service import ensure_bootstrap_admin_config, get_or_create_config

    if settings.database_url.startswith("sqlite"):
        database_path = engine.url.database
        if database_path and database_path != ":memory:":
            Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        admin = ensure_bootstrap_admin(db)
        _migrate_schema(admin.id)
        ensure_bootstrap_admin_config(db, admin.id)
        for (user_id,) in db.query(User.id).all():
            get_or_create_config(db, user_id)
    finally:
        db.close()


def _migrate_schema(admin_user_id: int):
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(generation_tasks)").fetchall()
        col_names = {row[1] for row in cols}
        if "strategy_config" not in col_names:
            conn.exec_driver_sql("ALTER TABLE generation_tasks ADD COLUMN strategy_config TEXT DEFAULT ''")
            conn.commit()
        if "tokens_used" not in col_names:
            conn.exec_driver_sql("ALTER TABLE generation_tasks ADD COLUMN tokens_used INTEGER DEFAULT 0")
            conn.commit()
        if "is_eval" not in col_names:
            conn.exec_driver_sql("ALTER TABLE generation_tasks ADD COLUMN is_eval BOOLEAN DEFAULT 0")
            conn.commit()
        if "stage" not in col_names:
            conn.exec_driver_sql("ALTER TABLE generation_tasks ADD COLUMN stage VARCHAR(100) DEFAULT ''")
            conn.commit()
        if "knowledge_refs" not in col_names:
            conn.exec_driver_sql("ALTER TABLE generation_tasks ADD COLUMN knowledge_refs TEXT DEFAULT ''")
            conn.commit()

        eval_run_tables = conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='eval_runs'"
        ).fetchall()
        if eval_run_tables:
            eval_run_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(eval_runs)").fetchall()}
            if "stage" not in eval_run_cols:
                conn.exec_driver_sql("ALTER TABLE eval_runs ADD COLUMN stage VARCHAR(100) DEFAULT ''")
                conn.commit()

        draft_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(generated_case_drafts)").fetchall()}
        if "is_smoke" not in draft_cols:
            conn.exec_driver_sql("ALTER TABLE generated_case_drafts ADD COLUMN is_smoke BOOLEAN DEFAULT 0")
            conn.commit()
        if "was_edited" not in draft_cols:
            conn.exec_driver_sql("ALTER TABLE generated_case_drafts ADD COLUMN was_edited BOOLEAN DEFAULT 0")
            # 存量数据：当前状态为 edited 的草稿补标
            conn.exec_driver_sql("UPDATE generated_case_drafts SET was_edited = 1 WHERE review_status = 'edited'")
            conn.commit()
        for col, ddl in [
            ("reject_reason", "ALTER TABLE generated_case_drafts ADD COLUMN reject_reason VARCHAR(200) DEFAULT ''"),
            ("judge_score", "ALTER TABLE generated_case_drafts ADD COLUMN judge_score FLOAT"),
            ("judge_issues", "ALTER TABLE generated_case_drafts ADD COLUMN judge_issues TEXT DEFAULT ''"),
        ]:
            if col not in draft_cols:
                conn.exec_driver_sql(ddl)
                conn.commit()

        config_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(system_config)").fetchall()}
        for col, ddl in [
            ("eval_llm_api_key", "ALTER TABLE system_config ADD COLUMN eval_llm_api_key VARCHAR(500) DEFAULT ''"),
            ("eval_llm_base_url", "ALTER TABLE system_config ADD COLUMN eval_llm_base_url VARCHAR(500) DEFAULT ''"),
            ("eval_llm_model", "ALTER TABLE system_config ADD COLUMN eval_llm_model VARCHAR(100) DEFAULT ''"),
            ("embedding_api_key", "ALTER TABLE system_config ADD COLUMN embedding_api_key VARCHAR(500) DEFAULT ''"),
            ("embedding_base_url", "ALTER TABLE system_config ADD COLUMN embedding_base_url VARCHAR(500) DEFAULT ''"),
            ("embedding_model", "ALTER TABLE system_config ADD COLUMN embedding_model VARCHAR(100) DEFAULT ''"),
        ]:
            if config_cols and col not in config_cols:
                conn.exec_driver_sql(ddl)
                conn.commit()
        if config_cols:
            # 旧版允许评测字段逐项回退。新版本为避免把生成 Key 发给另一域名，
            # 将历史不完整三元组清空，统一安全回退到生成模型。
            conn.exec_driver_sql(
                "UPDATE system_config SET "
                "eval_llm_api_key = '', eval_llm_base_url = '', eval_llm_model = '' "
                "WHERE ("
                "COALESCE(eval_llm_api_key, '') <> '' OR "
                "COALESCE(eval_llm_base_url, '') <> '' OR "
                "COALESCE(eval_llm_model, '') <> ''"
                ") AND NOT ("
                "COALESCE(eval_llm_api_key, '') <> '' AND "
                "COALESCE(eval_llm_base_url, '') <> '' AND "
                "COALESCE(eval_llm_model, '') <> ''"
                ")"
            )
            conn.commit()
        if config_cols and "user_id" not in config_cols:
            conn.exec_driver_sql("ALTER TABLE system_config ADD COLUMN user_id INTEGER")
        if config_cols:
            conn.exec_driver_sql(
                "UPDATE system_config SET user_id = ? WHERE user_id IS NULL",
                (admin_user_id,),
            )
            null_config_owner_count = conn.exec_driver_sql(
                "SELECT COUNT(*) FROM system_config WHERE user_id IS NULL"
            ).scalar_one()
            if null_config_owner_count:
                raise RuntimeError("模型配置归属迁移失败：仍有配置未关联用户")
            conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_system_config_user_id "
                "ON system_config (user_id)"
            )
            conn.commit()

        report_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(quality_reports)").fetchall()}
        for col, ddl in [
            ("avg_judge_score", "ALTER TABLE quality_reports ADD COLUMN avg_judge_score FLOAT"),
            ("hallucination_count", "ALTER TABLE quality_reports ADD COLUMN hallucination_count INTEGER DEFAULT 0"),
            ("duplicate_count", "ALTER TABLE quality_reports ADD COLUMN duplicate_count INTEGER DEFAULT 0"),
        ]:
            if col not in report_cols:
                conn.exec_driver_sql(ddl)
                conn.commit()

        tc_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(testcases)").fetchall()}
        if "is_smoke" not in tc_cols:
            conn.exec_driver_sql("ALTER TABLE testcases ADD COLUMN is_smoke BOOLEAN DEFAULT 0")
            conn.commit()

        project_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(projects)").fetchall()}
        if "is_eval" not in project_cols:
            conn.exec_driver_sql("ALTER TABLE projects ADD COLUMN is_eval BOOLEAN DEFAULT 0")
            conn.commit()
        if "user_id" not in project_cols:
            conn.exec_driver_sql("ALTER TABLE projects ADD COLUMN user_id INTEGER")
            conn.exec_driver_sql(
                "UPDATE projects SET user_id = ? WHERE user_id IS NULL",
                (admin_user_id,),
            )
        else:
            conn.exec_driver_sql(
                "UPDATE projects SET user_id = ? WHERE user_id IS NULL",
                (admin_user_id,),
            )
        null_owner_count = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM projects WHERE user_id IS NULL"
        ).scalar_one()
        if null_owner_count:
            raise RuntimeError("项目归属迁移失败：仍有项目未关联用户")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_projects_user_id ON projects (user_id)")
        conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_projects_user_eval "
            "ON projects (user_id) WHERE is_eval = 1"
        )
        conn.commit()

        # 「测试轮次」已升级为「测试任务 + 批次」，旧表按约定直接废弃
        conn.exec_driver_sql("DROP TABLE IF EXISTS test_run_cases")
        conn.exec_driver_sql("DROP TABLE IF EXISTS test_runs")
        conn.commit()

        doc_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(requirement_documents)").fetchall()}
        if "test_scope" not in doc_cols:
            conn.exec_driver_sql("ALTER TABLE requirement_documents ADD COLUMN test_scope TEXT DEFAULT ''")
            conn.commit()
        if "is_eval" not in doc_cols:
            conn.exec_driver_sql("ALTER TABLE requirement_documents ADD COLUMN is_eval BOOLEAN DEFAULT 0")
            conn.commit()
