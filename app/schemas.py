"""Pydantic-схемы API."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


class Page(BaseModel, Generic[T]):  # noqa: UP046 - совместимость с Pydantic
    items: list[T]
    total: int
    page: int
    per_page: int


# ---------------------------------------------------------------------------
# Пользователи и доступ
# ---------------------------------------------------------------------------
class UserBase(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(default="", max_length=255)
    role: Literal["admin", "manager", "viewer"] = "manager"
    is_active: bool = True
    telegram_chat_id: str = Field(default="", max_length=64)
    notify_email: bool = True
    notify_telegram: bool = False

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if "@" not in value:
            raise ValueError("Некорректный email")
        return value


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    role: Literal["admin", "manager", "viewer"] | None = None
    is_active: bool | None = None
    telegram_chat_id: str | None = Field(default=None, max_length=64)
    notify_email: bool | None = None
    notify_telegram: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserRead(ORMModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool
    telegram_chat_id: str
    notify_email: bool
    notify_telegram: bool
    created_at: datetime


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenRead(BaseModel):
    id: int
    name: str
    token: str | None = None
    expires_at: datetime | None = None
    created_at: datetime


class ApiTokenCreate(BaseModel):
    name: str = Field(default="API token", max_length=120)
    days: int | None = Field(default=365, ge=1, le=3650)


# ---------------------------------------------------------------------------
# Проекты
# ---------------------------------------------------------------------------
class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    description: str = ""
    status: Literal["active", "archived"] = "active"
    currency: str = Field(default="RUB", min_length=3, max_length=3)


class ProjectCreate(ProjectBase):
    owner_id: int | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: Literal["active", "archived"] | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    is_archived: bool | None = None


class ProjectRead(ORMModel):
    id: int
    name: str
    code: str
    description: str
    status: str
    currency: str
    owner_id: int | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class ProjectMemberCreate(BaseModel):
    user_id: int
    role: Literal["manager", "viewer"] = "manager"


class ProjectMemberRead(ORMModel):
    id: int
    project_id: int
    user_id: int
    role: str
    created_at: datetime


# ---------------------------------------------------------------------------
# Клиенты
# ---------------------------------------------------------------------------
class ClientBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    company: str = Field(default="", max_length=255)
    email: str = Field(default="", max_length=255)
    phone: str = Field(default="", max_length=64)
    status: Literal["new", "active", "inactive", "archived"] = "new"
    source: str = Field(default="", max_length=120)
    notes: str = ""
    owner_id: int | None = None


class ClientCreate(ClientBase):
    project_id: int | None = None


class ClientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    status: Literal["new", "active", "inactive", "archived"] | None = None
    source: str | None = Field(default=None, max_length=120)
    notes: str | None = None
    owner_id: int | None = None
    is_archived: bool | None = None


class ClientRead(ORMModel):
    id: int
    project_id: int
    name: str
    company: str
    email: str
    phone: str
    status: str
    source: str
    notes: str
    owner_id: int | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Сделки и заказы
# ---------------------------------------------------------------------------
class OrderItemBase(BaseModel):
    product_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_price: Decimal = Field(default=Decimal("0"), ge=0)


class OrderItemCreate(OrderItemBase):
    pass


class OrderItemRead(ORMModel):
    id: int
    deal_id: int
    product_id: int | None
    name: str
    quantity: Decimal
    unit_price: Decimal
    total: Decimal


class DealBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    client_id: int | None = None
    kind: Literal["deal", "order"] = "deal"
    amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    stage: Literal["new", "negotiation", "proposal", "won", "lost", "fulfilled"] = "new"
    description: str = ""
    owner_id: int | None = None


class DealCreate(DealBase):
    project_id: int | None = None


class DealUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    client_id: int | None = None
    kind: Literal["deal", "order"] | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    stage: Literal["new", "negotiation", "proposal", "won", "lost", "fulfilled"] | None = None
    description: str | None = None
    owner_id: int | None = None


class DealRead(ORMModel):
    id: int
    project_id: int
    client_id: int | None
    kind: str
    title: str
    amount: Decimal
    currency: str
    stage: str
    description: str
    owner_id: int | None
    fulfilled_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DealDetailRead(DealRead):
    items: list[OrderItemRead] = []


# ---------------------------------------------------------------------------
# Задачи
# ---------------------------------------------------------------------------
class TaskBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = ""
    client_id: int | None = None
    deal_id: int | None = None
    due_at: datetime | None = None
    priority: Literal["low", "normal", "high", "urgent"] = "normal"
    assigned_to_id: int | None = None


class TaskCreate(TaskBase):
    project_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    client_id: int | None = None
    deal_id: int | None = None
    due_at: datetime | None = None
    priority: Literal["low", "normal", "high", "urgent"] | None = None
    assigned_to_id: int | None = None
    is_completed: bool | None = None


class TaskRead(ORMModel):
    id: int
    project_id: int
    client_id: int | None
    deal_id: int | None
    title: str
    description: str
    due_at: datetime | None
    priority: str
    assigned_to_id: int | None
    is_completed: bool
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Платежи
# ---------------------------------------------------------------------------
class PaymentBase(BaseModel):
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    client_id: int | None = None
    deal_id: int | None = None
    description: str = Field(default="", max_length=255)
    method: Literal["manual", "robokassa"] = "manual"


class PaymentCreate(PaymentBase):
    project_id: int | None = None


class PaymentUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0)
    status: Literal["pending", "paid", "failed", "refunded", "canceled"] | None = None
    description: str | None = Field(default=None, max_length=255)
    client_id: int | None = None
    deal_id: int | None = None


class PaymentRead(ORMModel):
    id: int
    project_id: int
    client_id: int | None
    deal_id: int | None
    amount: Decimal
    currency: str
    status: str
    method: str
    inv_id: str | None
    robokassa_link: str
    description: str
    paid_at: datetime | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Склад
# ---------------------------------------------------------------------------
class ProductBase(BaseModel):
    sku: str = Field(default="", max_length=64)
    name: str = Field(min_length=1, max_length=255)
    unit: str = Field(default="шт", max_length=20)
    price: Decimal = Field(default=Decimal("0"), ge=0)
    cost: Decimal = Field(default=Decimal("0"), ge=0)
    min_stock: Decimal = Field(default=Decimal("0"), ge=0)
    is_active: bool = True


class ProductCreate(ProductBase):
    project_id: int | None = None


class ProductUpdate(BaseModel):
    sku: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    unit: str | None = Field(default=None, max_length=20)
    price: Decimal | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0)
    min_stock: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductRead(ORMModel):
    id: int
    project_id: int
    sku: str
    name: str
    unit: str
    price: Decimal
    cost: Decimal
    stock_qty: Decimal
    min_stock: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class StockMovementCreate(BaseModel):
    product_id: int
    movement_type: Literal["in", "out", "adjust"]
    quantity: Decimal = Field(gt=0)
    unit_cost: Decimal = Field(default=Decimal("0"), ge=0)
    reference: str = Field(default="", max_length=120)
    comment: str = Field(default="", max_length=255)
    project_id: int | None = None


class StockMovementRead(ORMModel):
    id: int
    project_id: int
    product_id: int
    movement_type: str
    quantity: Decimal
    unit_cost: Decimal
    reference: str
    comment: str
    created_by_id: int | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Учёт
# ---------------------------------------------------------------------------
class TransactionBase(BaseModel):
    type: Literal["income", "expense"]
    category: str = Field(default="", max_length=120)
    amount: Decimal = Field(gt=0)
    currency: str = Field(default="RUB", min_length=3, max_length=3)
    transaction_date: date
    description: str = Field(default="", max_length=255)
    deal_id: int | None = None


class TransactionCreate(TransactionBase):
    project_id: int | None = None


class TransactionUpdate(BaseModel):
    type: Literal["income", "expense"] | None = None
    category: str | None = Field(default=None, max_length=120)
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    transaction_date: date | None = None
    description: str | None = Field(default=None, max_length=255)
    deal_id: int | None = None


class TransactionRead(ORMModel):
    id: int
    project_id: int
    type: str
    category: str
    amount: Decimal
    currency: str
    transaction_date: date
    description: str
    payment_id: int | None
    deal_id: int | None
    created_by_id: int | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Отчёты и уведомления
# ---------------------------------------------------------------------------
class ReportGenerateRequest(BaseModel):
    report_type: Literal["summary", "sales", "finance", "warehouse", "tasks"] = "summary"
    period_from: date | None = None
    period_to: date | None = None
    project_id: int | None = None


class ReportRead(ORMModel):
    id: int
    project_id: int
    report_type: str
    period_from: date | None
    period_to: date | None
    spreadsheet_url: str
    summary: str
    status: str
    error: str
    created_by_id: int | None
    created_at: datetime


class ReportScheduleBase(BaseModel):
    report_type: Literal["summary", "sales", "finance", "warehouse", "tasks"] = "summary"
    cron_expression: str = Field(default="0 9 * * *", max_length=120)
    recipients_email: str = ""
    recipients_telegram: str = ""
    channels: str = Field(default="email", max_length=40)
    is_active: bool = True


class ReportScheduleCreate(ReportScheduleBase):
    project_id: int | None = None


class ReportScheduleUpdate(BaseModel):
    report_type: Literal["summary", "sales", "finance", "warehouse", "tasks"] | None = None
    cron_expression: str | None = Field(default=None, max_length=120)
    recipients_email: str | None = None
    recipients_telegram: str | None = None
    channels: str | None = Field(default=None, max_length=40)
    is_active: bool | None = None


class ReportScheduleRead(ORMModel):
    id: int
    project_id: int
    report_type: str
    cron_expression: str
    recipients_email: str
    recipients_telegram: str
    channels: str
    is_active: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_error: str
    created_by_id: int | None
    created_at: datetime
    updated_at: datetime


class GoogleDocCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    entity_type: str = Field(default="", max_length=40)
    entity_id: int | None = None
    body: str = ""


class GoogleSheetCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    entity_type: str = Field(default="", max_length=40)
    entity_id: int | None = None


class NotificationRead(ORMModel):
    id: int
    user_id: int | None
    project_id: int | None
    channel: str
    recipient: str
    subject: str
    body: str
    status: str
    attempts: int
    error: str
    created_at: datetime
    sent_at: datetime | None
