"""Создать резервную копию SQLite-базы Custom-CRM."""

from __future__ import annotations

from app.database import Database


def main() -> int:
    database = Database()
    database.create_all()
    path = database.backup()
    if path is None:
        print("Автоматическая копия доступна только для SQLite. Используйте pg_dump.")
        return 1
    print(f"Резервная копия создана: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
