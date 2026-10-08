from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.api.deps import current_user_id
from app.models.project import Project
from app.schemas import HomeOverviewOut, ProjectCreate, ProjectOut, ProjectStageOut, ProjectUpdate
from app.services.knowledge_service import delete_document_vectors
from app.services.project_service import compute_project_stage, get_home_overview

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/overview", response_model=HomeOverviewOut)
def get_overview(db: Session = Depends(get_db)):
    return get_home_overview(db, current_user_id(db))


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return (
        db.query(Project)
        .filter(Project.user_id == current_user_id(db), Project.is_eval == False)
        .order_by(Project.updated_at.desc())
        .all()
    )


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    project = Project(user_id=current_user_id(db), name=data.name, description=data.description)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user_id(db),
        Project.is_eval == False,
    ).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    return project


@router.get("/{project_id}/stage", response_model=ProjectStageOut)
def get_project_stage(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user_id(db),
        Project.is_eval == False,
    ).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    return compute_project_stage(db, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, data: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user_id(db),
        Project.is_eval == False,
    ).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    if data.name is not None:
        project.name = data.name
    if data.description is not None:
        project.description = data.description
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.user_id == current_user_id(db),
        Project.is_eval == False,
    ).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    # 先清理知识库向量，SQLite 复用主键时残留向量会污染新项目的检索
    for doc in project.knowledge_documents:
        delete_document_vectors(doc)
    db.delete(project)
    db.commit()
