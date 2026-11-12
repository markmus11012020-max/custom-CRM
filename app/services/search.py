"""Нормализация поисковых строк.

SQLite не поддерживает ILIKE, а LOWER() в SQLite не сворачивает кириллицу.
Поэтому храним нормализованный search_text, построенный через Python casefold().
"""

from __future__ import annotations

from sqlalchemy import event

from app.models import Client, Deal, Task


def normalize(*parts: object) -> str:
    values = [str(part).casefold().strip() for part in parts if part is not None and str(part).strip()]
    return " ".join(values)


def refresh_search_text(instance: Client | Deal | Task) -> None:
    if isinstance(instance, Client):
        instance.search_text = normalize(
            instance.name,
            instance.company,
            instance.email,
            instance.phone,
            instance.source,
            instance.notes,
        )
    elif isinstance(instance, Deal):
        # Не трогаем relationships внутри before_flush: это может вызвать lazy load.
        instance.search_text = normalize(
            instance.title,
            instance.description,
            instance.kind,
            instance.stage,
        )
    elif isinstance(instance, Task):
        instance.search_text = normalize(
            instance.title,
            instance.description,
            instance.priority,
        )


@event.listens_for(Client, "before_insert")
@event.listens_for(Client, "before_update")
def _client_search(mapper, connection, target):  # type: ignore[no-untyped-def]
    refresh_search_text(target)


@event.listens_for(Deal, "before_insert")
@event.listens_for(Deal, "before_update")
def _deal_search(mapper, connection, target):  # type: ignore[no-untyped-def]
    refresh_search_text(target)


@event.listens_for(Task, "before_insert")
@event.listens_for(Task, "before_update")
def _task_search(mapper, connection, target):  # type: ignore[no-untyped-def]
    refresh_search_text(target)
