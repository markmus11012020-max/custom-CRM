"""API проектов и участников."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, require_edit
from app.models import Project, ProjectMember, User
from app.schemas import (
    ProjectCreate,
    ProjectMemberCreate,
    ProjectMemberRead,
    ProjectRead,
    ProjectUpdate,
)
from app.services.access import (
    accessible_projects,
    ensure_project_member,
    get_project_for_user,
)
from app.services.activity import log_activity
from app.services.auth import require_admin

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectRead])
def list_projects(db: DbSession, user: CurrentUser):
    return accessible_projects(db, user)


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(payload: ProjectCreate, db: DbSession, user: User = Depends(require_admin)):
    if db.scalar(select(Project).where(Project.code == payload.code)):
        raise HTTPException(status_code=409, detail="Проект с таким кодом уже существует")
    project = Project(
        name=payload.name,
        code=payload.code,
        description=payload.description,
        status=payload.status,
        currency=payload.currency,
        owner_id=payload.owner_id or user.id,
    )
    db.add(project)
    db.flush()
    ensure_project_member(db, project, db.get(User, project.owner_id) or user, "manager")
    log_activity(
        db,
        action="project_created",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        user_id=user.id,
        details=project.name,
    )
    db.commit()
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: DbSession, user: CurrentUser):
    return get_project_for_user(db, project_id, user)


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: DbSession, user: CurrentUser):
    project = get_project_for_user(db, project_id, user)
    require_edit(db, project, user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    log_activity(
        db,
        action="project_updated",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        user_id=user.id,
    )
    db.commit()
    return project


@router.delete("/{project_id}")
def archive_project(project_id: int, db: DbSession, user: User = Depends(require_admin)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Проект не найден")
    project.is_archived = True
    project.status = "archived"
    log_activity(
        db,
        action="project_archived",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        user_id=user.id,
    )
    db.commit()
    return {"ok": True}


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
def list_members(project_id: int, db: DbSession, user: CurrentUser):
    get_project_for_user(db, project_id, user)
    return list(
        db.scalars(select(ProjectMember).where(ProjectMember.project_id == project_id))
    )


@router.post("/{project_id}/members", response_model=ProjectMemberRead, status_code=201)
def add_member(
    project_id: int,
    payload: ProjectMemberCreate,
    db: DbSession,
    user: CurrentUser,
):
    project = get_project_for_user(db, project_id, user)
    require_edit(db, project, user)
    target = db.get(User, payload.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == payload.user_id
        )
    )
    if member:
        member.role = payload.role
    else:
        member = ProjectMember(project_id=project_id, user_id=payload.user_id, role=payload.role)
        db.add(member)
        db.flush()
    db.commit()
    return member


@router.delete("/{project_id}/members/{member_id}")
def remove_member(project_id: int, member_id: int, db: DbSession, user: CurrentUser):
    project = get_project_for_user(db, project_id, user)
    require_edit(db, project, user)
    member = db.get(ProjectMember, member_id)
    if member is None or member.project_id != project_id:
        raise HTTPException(status_code=404, detail="Участник не найден")
    if project.owner_id == member.user_id:
        raise HTTPException(status_code=409, detail="Нельзя удалить владельца проекта")
    db.delete(member)
    db.commit()
    return {"ok": True}
