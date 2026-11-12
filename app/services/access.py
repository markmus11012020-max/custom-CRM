"""Проверка ролей и доступа к проектам."""

from __future__ import annotations

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project, ProjectMember, User


def is_admin(user: User) -> bool:
    return user.role == "admin"


def is_manager(user: User) -> bool:
    return user.role in {"admin", "manager"}


def project_role(db: Session, project_id: int, user: User) -> str | None:
    if is_admin(user):
        return "admin"
    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user.id
        )
    )
    return member.role if member else None


def accessible_projects(db: Session, user: User) -> list[Project]:
    query = select(Project).where(Project.is_archived.is_(False)).order_by(Project.name)
    if not is_admin(user):
        query = (
            query.join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user.id)
            .distinct()
        )
    return list(db.scalars(query))


def accessible_project_ids(db: Session, user: User) -> list[int]:
    return [project.id for project in accessible_projects(db, user)]


def get_project_for_user(db: Session, project_id: int, user: User) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Проект не найден")
    if not is_admin(user) and project_role(db, project.id, user) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа к проекту")
    return project


def can_edit_project(db: Session, project_id: int, user: User) -> bool:
    if is_admin(user):
        return True
    return project_role(db, project_id, user) == "manager"


def require_project_edit(db: Session, project_id: int, user: User) -> None:
    if not can_edit_project(db, project_id, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Недостаточно прав")


def get_active_project(request: Request, db: Session, user: User) -> Project:
    projects = accessible_projects(db, user)
    if not projects:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нет доступных проектов. Обратитесь к администратору.",
        )
    active_id = request.session.get("active_project_id")
    for project in projects:
        if project.id == active_id:
            return project
    project = projects[0]
    request.session["active_project_id"] = project.id
    return project


def set_active_project(request: Request, db: Session, user: User, project_id: int) -> Project:
    project = get_project_for_user(db, project_id, user)
    request.session["active_project_id"] = project.id
    return project


def ensure_project_member(db: Session, project: Project, user: User, role: str = "manager") -> ProjectMember:
    member = db.scalar(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id, ProjectMember.user_id == user.id
        )
    )
    if member is None:
        member = ProjectMember(project_id=project.id, user_id=user.id, role=role)
        db.add(member)
        db.flush()
    return member
