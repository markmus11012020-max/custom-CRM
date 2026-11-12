"""ORM-модели Custom-CRM (SQLAlchemy 2.0)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


# ---------------------------------------------------------------------------
# Пользователи и доступ
# ---------------------------------------------------------------------------
class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="manager")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    telegram_chat_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    notify_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_telegram: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    api_tokens: Mapped[list[ApiToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    memberships: Mapped[list[ProjectMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="API token")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="api_tokens")


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    owner: Mapped[User | None] = relationship()
    members: Mapped[list[ProjectMember]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    clients: Mapped[list[Client]] = relationship(back_populates="project", cascade="all, delete-orphan")
    deals: Mapped[list[Deal]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tasks: Mapped[list[Task]] = relationship(back_populates="project", cascade="all, delete-orphan")
    payments: Mapped[list[Payment]] = relationship(back_populates="project", cascade="all, delete-orphan")
    products: Mapped[list[Product]] = relationship(back_populates="project", cascade="all, delete-orphan")
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    reports: Mapped[list[Report]] = relationship(back_populates="project", cascade="all, delete-orphan")
    schedules: Mapped[list[ReportSchedule]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_project_member"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="manager")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


# ---------------------------------------------------------------------------
# CRM
# ---------------------------------------------------------------------------
class Client(TimestampMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (
        Index("ix_clients_project_status", "project_id", "status"),
        Index("ix_clients_project_archived", "project_id", "is_archived"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    source: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    project: Mapped[Project] = relationship(back_populates="clients")
    owner: Mapped[User | None] = relationship()
    deals: Mapped[list[Deal]] = relationship(
        back_populates="client", passive_deletes=True
    )
    tasks: Mapped[list[Task]] = relationship(back_populates="client", passive_deletes=True)
    payments: Mapped[list[Payment]] = relationship(back_populates="client", passive_deletes=True)


class Deal(TimestampMixin, Base):
    __tablename__ = "deals"
    __table_args__ = (
        Index("ix_deals_project_stage", "project_id", "stage"),
        Index("ix_deals_project_created", "project_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="deal")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    stage: Mapped[str] = mapped_column(String(20), nullable=False, default="new")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    project: Mapped[Project] = relationship(back_populates="deals")
    client: Mapped[Client | None] = relationship(back_populates="deals")
    owner: Mapped[User | None] = relationship()
    items: Mapped[list[OrderItem]] = relationship(
        back_populates="deal", cascade="all, delete-orphan", order_by="OrderItem.id"
    )
    tasks: Mapped[list[Task]] = relationship(back_populates="deal", passive_deletes=True)
    payments: Mapped[list[Payment]] = relationship(back_populates="deal", passive_deletes=True)
    transactions: Mapped[list[Transaction]] = relationship(back_populates="deal", passive_deletes=True)


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deal_id: Mapped[int] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("1"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    deal: Mapped[Deal] = relationship(back_populates="items")
    product: Mapped[Product | None] = relationship()


class Task(TimestampMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_project_due", "project_id", "due_at", "is_completed"),
        Index("ix_tasks_project_assigned", "project_id", "assigned_to_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), index=True, nullable=True
    )
    deal_id: Mapped[int | None] = mapped_column(
        ForeignKey("deals.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    assigned_to_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    search_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    project: Mapped[Project] = relationship(back_populates="tasks")
    client: Mapped[Client | None] = relationship(back_populates="tasks")
    deal: Mapped[Deal | None] = relationship(back_populates="tasks")
    assigned_to: Mapped[User | None] = relationship()


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_project_status", "project_id", "status"),
        Index("ix_payments_project_created", "project_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("clients.id", ondelete="SET NULL"), index=True, nullable=True
    )
    deal_id: Mapped[int | None] = mapped_column(
        ForeignKey("deals.id", ondelete="SET NULL"), index=True, nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    method: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    inv_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    robokassa_link: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="payments")
    client: Mapped[Client | None] = relationship(back_populates="payments")
    deal: Mapped[Deal | None] = relationship(back_populates="payments")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="payment")


# ---------------------------------------------------------------------------
# Склад
# ---------------------------------------------------------------------------
class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("project_id", "sku", name="uq_product_project_sku"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False, default="шт")
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    stock_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    min_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    project: Mapped[Project] = relationship(back_populates="products")
    movements: Mapped[list[StockMovement]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class StockMovement(Base):
    __tablename__ = "stock_movements"
    __table_args__ = (Index("ix_stock_project_created", "project_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    movement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=Decimal("0"))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    reference: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    comment: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    product: Mapped[Product] = relationship(back_populates="movements")
    created_by: Mapped[User | None] = relationship()


# ---------------------------------------------------------------------------
# Управленческий учёт
# ---------------------------------------------------------------------------
class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("payment_id", "type", name="uq_transaction_payment_type"),
        Index("ix_transactions_project_date", "project_id", "transaction_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    payment_id: Mapped[int | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )
    deal_id: Mapped[int | None] = mapped_column(
        ForeignKey("deals.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="transactions")
    payment: Mapped[Payment | None] = relationship(back_populates="transactions")
    deal: Mapped[Deal | None] = relationship(back_populates="transactions")
    created_by: Mapped[User | None] = relationship()


# ---------------------------------------------------------------------------
# Отчёты и уведомления
# ---------------------------------------------------------------------------
class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    report_type: Mapped[str] = mapped_column(String(40), nullable=False, default="summary")
    period_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    spreadsheet_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="generated")
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    project: Mapped[Project] = relationship(back_populates="reports")
    created_by: Mapped[User | None] = relationship()


class ReportSchedule(TimestampMixin, Base):
    __tablename__ = "report_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    report_type: Mapped[str] = mapped_column(String(40), nullable=False, default="summary")
    cron_expression: Mapped[str] = mapped_column(String(120), nullable=False, default="0 9 * * *")
    recipients_email: Mapped[str] = mapped_column(Text, nullable=False, default="")
    recipients_telegram: Mapped[str] = mapped_column(Text, nullable=False, default="")
    channels: Mapped[str] = mapped_column(String(40), nullable=False, default="email")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped[Project] = relationship(back_populates="schedules")
    created_by: Mapped[User | None] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="email")
    recipient: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    subject: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dedupe_key: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User | None] = relationship()
    project: Mapped[Project | None] = relationship()


# ---------------------------------------------------------------------------
# Интеграции и системные данные
# ---------------------------------------------------------------------------
class GoogleFile(Base):
    __tablename__ = "google_files"
    __table_args__ = (Index("ix_google_files_entity", "entity_type", "entity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    file_id: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    web_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ActivityLog(Base):
    __tablename__ = "activity_log"
    __table_args__ = (Index("ix_activity_project_created", "project_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User | None] = relationship()
    project: Mapped[Project | None] = relationship()


class AppSetting(Base):
    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
