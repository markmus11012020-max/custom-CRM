"""Слой базы данных: SQLAlchemy-движок, сессии, инициализация и seed."""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import BASE_DIR, Settings, get_logger, get_settings
from app.models import (
    ActivityLog,
    AppSetting,
    Base,
    Client,
    Deal,
    OrderItem,
    Payment,
    Product,
    Project,
    ProjectMember,
    Task,
    Transaction,
    User,
)
from app.security import hash_password
from app.services import search as _search  # noqa: F401 - регистрирует event listeners

LOGGER = get_logger("database")


def _absolute_sqlite_url(url: str) -> str:
    """Сделать относительный путь SQLite абсолютным от корня проекта."""
    prefix = "sqlite:///"
    if not url.startswith(prefix) or ":memory:" in url:
        return url
    raw = url[len(prefix) :]
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return prefix + path.as_posix()


class Database:
    """Обёртка над SQLAlchemy: SQLite по умолчанию, PostgreSQL по DATABASE_URL."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        url = _absolute_sqlite_url(self.settings.database_url)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=not url.startswith("sqlite"),
            future=True,
        )
        if url.startswith("sqlite"):
            self._configure_sqlite(self.engine)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )

    @staticmethod
    def _configure_sqlite(engine: Engine) -> None:
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def healthcheck(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True
        except Exception as exc:  # noqa: BLE001
            LOGGER.error("Healthcheck БД не прошёл: %s", exc)
            return False

    # ------------------------------------------------------------------
    def get_setting(self, key: str, default: str = "") -> str:
        with self.session_scope() as session:
            row = session.scalar(select(AppSetting).where(AppSetting.key == key))
            return row.value if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.session_scope() as session:
            row = session.scalar(select(AppSetting).where(AppSetting.key == key))
            if row is None:
                session.add(AppSetting(key=key, value=value))
            else:
                row.value = value

    # ------------------------------------------------------------------
    def seed(self) -> None:
        """Создать администратора, основной проект и демо-данные."""
        with self.session_scope() as session:
            admin = session.scalar(select(User).where(User.email == self.settings.admin_email))
            if admin is None:
                admin = User(
                    email=self.settings.admin_email,
                    password_hash=hash_password(self.settings.admin_password),
                    full_name=self.settings.admin_name,
                    role="admin",
                    is_active=True,
                )
                session.add(admin)
                session.flush()
                LOGGER.info("Создан администратор %s", admin.email)

            project = session.scalar(select(Project).where(Project.code == "main"))
            if project is None:
                project = Project(
                    name="Основной проект",
                    code="main",
                    description="Базовый проект Custom-CRM",
                    status="active",
                    currency="RUB",
                    owner_id=admin.id,
                )
                session.add(project)
                session.flush()
                session.add(ProjectMember(project_id=project.id, user_id=admin.id, role="manager"))

            if self.settings.seed_demo:
                self._seed_demo(session, project, admin)

    def _seed_demo(self, session: Session, project: Project, admin: User) -> None:
        if session.scalar(select(Client.id).where(Client.project_id == project.id).limit(1)):
            return

        clients = [
            Client(
                project_id=project.id,
                name="Иван Петров",
                company="ООО Ромашка",
                email="ivan@romashka.ru",
                phone="+7 900 100-10-10",
                status="active",
                source="Сайт",
                notes="Интересуется автоматизацией продаж.",
                owner_id=admin.id,
                search_text="иван петров ооо ромашка ivan@romashka.ru +7 900 100-10-10 автоматизацией продаж",
            ),
            Client(
                project_id=project.id,
                name="Анна Смирнова",
                company="ИП Смирнова",
                email="anna@smirnova.ru",
                phone="+7 900 200-20-20",
                status="new",
                source="Рекомендация",
                notes="Нужны юридические документы.",
                owner_id=admin.id,
                search_text="анна смирнова ип смирнова anna@smirnova.ru +7 900 200-20-20 юридические документы",
            ),
            Client(
                project_id=project.id,
                name="TechStart",
                company="ООО ТехСтарт",
                email="hello@techstart.ru",
                phone="+7 900 300-30-30",
                status="active",
                source="Конференция",
                notes="Потенциально крупный заказ на отчётность.",
                owner_id=admin.id,
                search_text="techstart ооо техстарт hello@techstart.ru +7 900 300-30-30 отчётность",
            ),
        ]
        session.add_all(clients)
        session.flush()

        deals = [
            Deal(
                project_id=project.id,
                client_id=clients[0].id,
                kind="deal",
                title="Внедрение CRM",
                amount=Decimal("150000"),
                stage="negotiation",
                description="Настройка воронки и обучение команды.",
                owner_id=admin.id,
                search_text="внедрение crm настройка воронки обучение",
            ),
            Deal(
                project_id=project.id,
                client_id=clients[1].id,
                kind="deal",
                title="Юридическое сопровождение",
                amount=Decimal("60000"),
                stage="proposal",
                description="Подготовка договора и претензии.",
                owner_id=admin.id,
                search_text="юридическое сопровождение договор претензия",
            ),
            Deal(
                project_id=project.id,
                client_id=clients[2].id,
                kind="order",
                title="Автоматизация отчётности",
                amount=Decimal("240000"),
                stage="won",
                description="Отчёты в Google Sheets и Telegram-уведомления.",
                owner_id=admin.id,
                search_text="автоматизация отчётности google sheets telegram",
            ),
        ]
        session.add_all(deals)
        session.flush()

        products = [
            Product(
                project_id=project.id,
                sku="CONSULT",
                name="Консультация",
                unit="час",
                price=Decimal("5000"),
                cost=Decimal("1500"),
                stock_qty=Decimal("100"),
                min_stock=Decimal("10"),
            ),
            Product(
                project_id=project.id,
                sku="MODULE",
                name="Разработка модуля",
                unit="шт",
                price=Decimal("80000"),
                cost=Decimal("30000"),
                stock_qty=Decimal("5"),
                min_stock=Decimal("2"),
            ),
            Product(
                project_id=project.id,
                sku="SUPPORT",
                name="Подписка на поддержку",
                unit="мес",
                price=Decimal("15000"),
                cost=Decimal("4000"),
                stock_qty=Decimal("20"),
                min_stock=Decimal("5"),
            ),
        ]
        session.add_all(products)
        session.flush()

        session.add(
            OrderItem(
                deal_id=deals[2].id,
                product_id=products[1].id,
                name=products[1].name,
                quantity=Decimal("2"),
                unit_price=Decimal("80000"),
                total=Decimal("160000"),
            )
        )
        session.add(
            OrderItem(
                deal_id=deals[2].id,
                product_id=products[2].id,
                name=products[2].name,
                quantity=Decimal("4"),
                unit_price=Decimal("15000"),
                total=Decimal("60000"),
            )
        )

        now = datetime.now(UTC)
        session.add_all(
            [
                Task(
                    project_id=project.id,
                    client_id=clients[0].id,
                    deal_id=deals[0].id,
                    title="Позвонить Ивану и уточнить бюджет",
                    description="Обсудить этапы внедрения.",
                    due_at=now - timedelta(days=1),
                    priority="high",
                    assigned_to_id=admin.id,
                    search_text="позвонить ивану уточнить бюджет внедрение",
                ),
                Task(
                    project_id=project.id,
                    client_id=clients[1].id,
                    title="Подготовить проект договора",
                    description="Согласовать с юристом.",
                    due_at=now + timedelta(days=1),
                    priority="normal",
                    assigned_to_id=admin.id,
                    search_text="подготовить проект договора юрист",
                ),
                Task(
                    project_id=project.id,
                    client_id=clients[2].id,
                    deal_id=deals[2].id,
                    title="Согласовать структуру отчёта",
                    description="Показать макет руководителю.",
                    due_at=now + timedelta(days=3),
                    priority="urgent",
                    assigned_to_id=admin.id,
                    search_text="согласовать структуру отчёта макет руководитель",
                ),
            ]
        )

        session.add_all(
            [
                Payment(
                    project_id=project.id,
                    client_id=clients[2].id,
                    deal_id=deals[2].id,
                    amount=Decimal("240000"),
                    status="paid",
                    method="manual",
                    description="Оплата проекта автоматизации",
                    paid_at=now - timedelta(days=2),
                ),
                Payment(
                    project_id=project.id,
                    client_id=clients[0].id,
                    deal_id=deals[0].id,
                    amount=Decimal("150000"),
                    status="pending",
                    method="robokassa",
                    description="Счёт на внедрение CRM",
                ),
            ]
        )
        session.flush()
        paid = session.scalars(
            select(Payment).where(Payment.project_id == project.id, Payment.status == "paid")
        ).first()
        if paid:
            session.add(
                Transaction(
                    project_id=project.id,
                    type="income",
                    category="Оплата проекта",
                    amount=paid.amount,
                    transaction_date=date.today() - timedelta(days=2),
                    description="Поступление по проекту автоматизации",
                    payment_id=paid.id,
                    deal_id=deals[2].id,
                    created_by_id=admin.id,
                )
            )
        session.add(
            Transaction(
                project_id=project.id,
                type="expense",
                category="Подрядчики",
                amount=Decimal("45000"),
                transaction_date=date.today() - timedelta(days=5),
                description="Оплата подрядчику за дизайн",
                created_by_id=admin.id,
            )
        )

        session.add(
            ActivityLog(
                project_id=project.id,
                user_id=admin.id,
                entity_type="project",
                entity_id=project.id,
                action="seed",
                details="Созданы демонстрационные данные",
            )
        )
        LOGGER.info("Демо-данные созданы в проекте %s", project.code)

    # ------------------------------------------------------------------
    def backup(self, destination: Path | None = None) -> Path | None:
        """Создать резервную копию SQLite. Для PostgreSQL вернуть None."""
        if not self.settings.is_sqlite:
            LOGGER.warning("Автоматический backup реализован для SQLite; используйте pg_dump")
            return None
        url = _absolute_sqlite_url(self.settings.database_url)
        source = Path(url.replace("sqlite:///", ""))
        if not source.exists():
            return None
        destination = destination or (
            BASE_DIR / "data" / "backups" / f"crm-{datetime.now().strftime('%Y%m%d-%H%M%S')}.db"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.engine.connect() as connection:
            connection.execute(text("PRAGMA wal_checkpoint(FULL)"))
        shutil.copy2(source, destination)
        return destination


def get_db(request: Request) -> Iterator[Session]:
    database: Database = request.app.state.db
    session = database.session_factory()
    try:
        yield session
    finally:
        session.close()
