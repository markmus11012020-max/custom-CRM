"""Генератор технического задания Custom-CRM в PDF и plain-text.

Запуск:
    python scripts/generate_tz_pdf.py

Результат:
    ТехЗадание.pdf
    docs/technical-spec.txt
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

BASE_DIR = Path(__file__).resolve().parent.parent
PDF_PATH = BASE_DIR / "ТехЗадание.pdf"
TXT_PATH = BASE_DIR / "docs" / "technical-spec.txt"

FONT_REGULAR = r"C:\Windows\Fonts\arial.ttf"
FONT_BOLD = r"C:\Windows\Fonts\arialbd.ttf"
FONT_MONO = r"C:\Windows\Fonts\consola.ttf"

PRIMARY = colors.HexColor("#4338CA")
ACCENT = colors.HexColor("#0D9488")
TEXT = colors.HexColor("#0F172A")
MUTED = colors.HexColor("#475569")
BORDER = colors.HexColor("#E2E8F0")
SOFT = colors.HexColor("#F7F8FC")
WHITE = colors.white


def p(text: str, style: str = "Body") -> Paragraph:
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), STYLES[style])


def bullets(items: list[str], style: str = "Bullet") -> list[Paragraph]:
    return [Paragraph("• " + escape(str(item)), STYLES[style]) for item in items]


def numbered(items: list[str]) -> list[Paragraph]:
    return [
        Paragraph(f"{index}. " + escape(str(item)), STYLES["Bullet"])
        for index, item in enumerate(items, 1)
    ]


def make_table(rows: list[list[str]], widths: list[float] | None = None) -> Table:
    data = []
    for row_index, row in enumerate(rows):
        style = "TableHeader" if row_index == 0 else "TableText"
        data.append([Paragraph(escape(str(cell)).replace("\n", "<br/>"), STYLES[style]) for cell in row])
    if widths is None:
        column_count = len(rows[0]) if rows else 1
        widths = [17.4 / column_count * cm] * column_count
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT]),
            ]
        )
    )
    return table


STYLES = {
    "Title": ParagraphStyle(
        "Title",
        fontName="Arial-Bold",
        fontSize=26,
        leading=32,
        textColor=PRIMARY,
        alignment=TA_CENTER,
        spaceAfter=10,
    ),
    "Subtitle": ParagraphStyle(
        "Subtitle",
        fontName="Arial",
        fontSize=14,
        leading=20,
        textColor=TEXT,
        alignment=TA_CENTER,
        spaceAfter=18,
    ),
    "Meta": ParagraphStyle(
        "Meta",
        fontName="Arial",
        fontSize=9,
        leading=13,
        textColor=MUTED,
        alignment=TA_CENTER,
    ),
    "H1": ParagraphStyle(
        "H1",
        fontName="Arial-Bold",
        fontSize=16,
        leading=20,
        textColor=PRIMARY,
        spaceBefore=6,
        spaceAfter=10,
    ),
    "H2": ParagraphStyle(
        "H2",
        fontName="Arial-Bold",
        fontSize=12,
        leading=16,
        textColor=TEXT,
        spaceBefore=10,
        spaceAfter=5,
    ),
    "H3": ParagraphStyle(
        "H3",
        fontName="Arial-Bold",
        fontSize=10.5,
        leading=14,
        textColor=TEXT,
        spaceBefore=8,
        spaceAfter=3,
    ),
    "Body": ParagraphStyle(
        "Body",
        fontName="Arial",
        fontSize=9.5,
        leading=14,
        textColor=TEXT,
        alignment=TA_LEFT,
        spaceAfter=5,
    ),
    "Bullet": ParagraphStyle(
        "Bullet",
        fontName="Arial",
        fontSize=9.5,
        leading=13.5,
        textColor=TEXT,
        leftIndent=12,
        bulletIndent=2,
        spaceAfter=2,
    ),
    "Small": ParagraphStyle(
        "Small",
        fontName="Arial",
        fontSize=8,
        leading=11,
        textColor=MUTED,
        spaceAfter=3,
    ),
    "Note": ParagraphStyle(
        "Note",
        fontName="Arial",
        fontSize=9,
        leading=13,
        textColor=TEXT,
        backColor=colors.HexColor("#EEF2FF"),
        borderColor=colors.HexColor("#C7D2FE"),
        borderWidth=0.6,
        borderPadding=7,
        spaceBefore=6,
        spaceAfter=8,
    ),
    "TableText": ParagraphStyle(
        "TableText",
        fontName="Arial",
        fontSize=8,
        leading=10.5,
        textColor=TEXT,
    ),
    "TableHeader": ParagraphStyle(
        "TableHeader",
        fontName="Arial-Bold",
        fontSize=8,
        leading=10.5,
        textColor=WHITE,
    ),
    "TOC0": ParagraphStyle(
        "TOC0",
        fontName="Arial-Bold",
        fontSize=10,
        leading=15,
        textColor=TEXT,
        leftIndent=0,
    ),
    "TOC1": ParagraphStyle(
        "TOC1",
        fontName="Arial",
        fontSize=9,
        leading=13,
        textColor=MUTED,
        leftIndent=14,
    ),
}


class TechSpecDoc(BaseDocTemplate):
    def __init__(self, filename: str, **kwargs) -> None:
        super().__init__(filename, **kwargs)
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="normal",
        )
        self.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=self._decorate)])

    def _decorate(self, canvas, doc) -> None:
        if doc.page == 1:
            return
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(1.8 * cm, A4[1] - 1.35 * cm, A4[0] - 1.8 * cm, A4[1] - 1.35 * cm)
        canvas.setFont("Arial", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(1.8 * cm, A4[1] - 1.15 * cm, "Custom-CRM — Техническое задание")
        canvas.drawRightString(A4[0] - 1.8 * cm, 1.0 * cm, f"Страница {doc.page}")
        canvas.restoreState()

    def afterFlowable(self, flowable) -> None:
        if isinstance(flowable, Paragraph):
            style = flowable.style.name
            if style in ("H1", "H2"):
                level = 0 if style == "H1" else 1
                text = flowable.getPlainText()
                self.notify("TOCEntry", (level, text, self.page))


BLOCKS = [
    ("title", "Техническое задание"),
    ("subtitle", "на разработку универсальной мини-CRM «Custom-CRM»"),
    (
        "meta",
        [
            ("Версия документа", "1.0"),
            ("Дата", "12.11.2026"),
            ("Статус", "Утверждено"),
            ("Заказчик", "Локальный бизнес / владелец проекта"),
            ("Исполнитель", "AI-разработка (OpenCode)"),
            ("Репозиторий", "https://github.com/markmus11012020-max/custom-CRM.git"),
        ],
    ),
    ("note", "Документ подготовлен на основе шаблона технического задания и расширенного набора требований заказчика. Все перечисленные функции входят в согласованный объём проекта."),
    ("pagebreak",),
    ("h1", "Содержание"),
    ("toc",),
    ("pagebreak",),

    ("h1", "1. Общие сведения"),
    ("h2", "1.1. Наименование и обозначение ПО"),
    ("p", "Полное наименование: «Универсальная мини-CRM Custom-CRM». Краткое наименование: Custom-CRM. Условное обозначение: CRM. Репозиторий проекта: https://github.com/markmus11012020-max/custom-CRM.git."),
    ("h2", "1.2. Назначение ПО"),
    ("p", "Custom-CRM — локальное или серверное веб-приложение для управления клиентами, проектами, сделками, заказами, задачами, платежами, складскими остатками и управленческим учётом. Система объединяет операционную работу менеджеров и аналитику руководителя в одном интерфейсе."),
    ("h2", "1.3. Область применения"),
    ("bullets", [
        "малый и средний бизнес, агентства, консалтинг, юридические и сервисные компании;",
        "личный бизнес владельца и команда до 20 пользователей;",
        "локальная установка на Windows с SQLite или серверная установка с PostgreSQL;",
        "работа через браузер, без установки клиентского приложения.",
    ]),
    ("h2", "1.4. Термины и сокращения"),
    ("table", [
        ["Термин", "Определение"],
        ["Проект", "Изолированная рабочая область с клиентами, сделками, задачами, платежами и отчётами."],
        ["Клиент", "Физическое или юридическое лицо, с которым ведётся взаимодействие."],
        ["Сделка", "Потенциальная или состоявшаяся продажа, привязанная к клиенту или проекту."],
        ["Заказ", "Сделка с позициями и последующим списанием товаров со склада."],
        ["Задача", "Действие или напоминание, связанное с клиентом, сделкой или проектом."],
        ["Платёж", "Счёт или транзакция оплаты, в том числе через Robokassa."],
        ["Складская операция", "Приход, расход или корректировка остатка товара."],
        ["Управленческая транзакция", "Доход или расход проекта для расчёта прибыли."],
        ["Отчёт", "Сводка данных CRM в Google Таблице, CSV или PDF-представлении."],
        ["Расписание", "Cron-правило автоматической генерации отчёта."],
        ["OAuth2", "Авторизация Google от имени личного аккаунта пользователя."],
        ["RBAC", "Ролевое управление доступом (администратор, менеджер, наблюдатель)."],
    ], [3.2 * cm, 14.2 * cm]),
    ("h2", "1.5. Роли пользователей"),
    ("table", [
        ["Роль", "Права"],
        ["Администратор", "Полный доступ: пользователи, проекты, настройки, интеграции, все данные, резервные копии."],
        ["Менеджер", "CRUD клиентов, сделок, задач, платежей, склада и транзакций в проектах, где он участник."],
        ["Наблюдатель", "Только чтение данных проектов, где он участник; экспорт отчётов."],
    ], [3.2 * cm, 14.2 * cm]),
    ("h2", "1.6. Режимы эксплуатации"),
    ("bullets", [
        "Локальный режим: Windows 10/11, Docker Desktop, SQLite, запуск через start.bat.",
        "Серверный режим: Linux, Docker Compose, PostgreSQL, доступ через браузер.",
        "Режим разработки: монтирование кода в контейнер, Uvicorn reload, hot reload шаблонов и статики.",
    ]),
    ("h2", "1.7. Ограничения"),
    ("bullets", [
        "Custom-CRM является инструментом управленческого учёта, а не заменой 1С или бухгалтерской программе.",
        "Robokassa подключается в тестовом режиме; для реальных платежей требуются боевые merchant-реквизиты и публичный ResultURL.",
        "Google-интеграция требует включённых API, согласия OAuth2 и доступа сервисного аккаунта к папке и таблице.",
        "Планировщик рассчитан на один экземпляр приложения; при горизонтальном масштабировании требуется внешний планировщик или блокировка.",
        "Мобильное приложение и офлайн-режим в объём не входят.",
    ]),

    ("h1", "2. Цели и назначение"),
    ("h2", "2.1. Цели"),
    ("bullets", [
        "сократить время на ведение клиентов и сделок за счёт единого интерфейса;",
        "обеспечить прозрачную воронку продаж и контроль задач;",
        "связать продажи, платежи, склад и управленческие финансы;",
        "автоматизировать подготовку отчётов и уведомлений;",
        "дать универсальную основу, которую можно развернуть локально или на сервере.",
    ]),
    ("h2", "2.2. Задачи"),
    ("bullets", [
        "реализовать многопроектную CRM с ролевым доступом;",
        "реализовать CRUD для клиентов, сделок, заказов, задач и платежей;",
        "реализовать складской учёт и позиции заказов;",
        "реализовать управленческий учёт доходов и расходов;",
        "реализовать поиск, фильтры, пагинацию и экспорт;",
        "реализовать Google Drive, Google Docs и Google Sheets;",
        "реализовать Robokassa, email и Telegram-уведомления;",
        "реализовать планировщик отчётов и напоминаний;",
        "обеспечить запуск через Docker и start.bat.",
    ]),
    ("h2", "2.3. Критерии успеха"),
    ("bullets", [
        "пользователь входит в систему и видит только доступные проекты;",
        "менеджер ведёт клиента от первого контакта до оплаты и выполнения заказа;",
        "руководитель видит воронку, финансы, склад и задачи без ручной сверки;",
        "отчёт формируется в Google Таблице одной кнопкой и по расписанию;",
        "уведомление приходит на email или в Telegram;",
        "проект запускается одной командой и обновляется без пересборки контейнера.",
    ]),

    ("h1", "3. Функциональные требования"),
    ("h2", "3.1. Аутентификация, пользователи и роли"),
    ("bullets", [
        "Система должна поддерживать вход по email и паролю, выход и смену пароля.",
        "Пароли должны храниться только в виде хеша Argon2; открытый пароль не сохраняется и не логируется.",
        "Сессия должна храниться в подписанной HttpOnly cookie; для API должен поддерживаться Bearer-токен.",
        "Администратор должен создавать, блокировать и редактировать пользователей, назначать роли.",
        "Должны поддерживаться роли admin, manager, viewer и проверка прав на каждом маршруте.",
        "Должны поддерживаться персональные API-токены с датой истечения и отзывом.",
        "Все изменения критичных сущностей должны попадать в журнал активности.",
    ]),
    ("h2", "3.2. Проекты и мультипроектность"),
    ("bullets", [
        "Система должна поддерживать несколько проектов с названием, кодом, описанием, валютой и статусом.",
        "Пользователь должен переключать активный проект; все списки и KPI фильтруются по проекту.",
        "Администратор видит все проекты; менеджер и наблюдатель — только проекты, где они участники.",
        "Должны поддерживаться участники проекта и их роли.",
        "Проект должен архивироваться без удаления связанных данных.",
        "Удаление проекта должно требовать подтверждения и быть недоступно при наличии связанных записей, если не выбрано каскадное удаление.",
    ]),
    ("h2", "3.3. Клиенты"),
    ("bullets", [
        "CRUD клиентов: имя, компания, email, телефон, статус, источник, ответственный, заметки.",
        "Статусы клиента: новый, активный, неактивный, архив.",
        "Мягкое архивирование и восстановление; жёсткое удаление только администратором.",
        "Карточка клиента: сделки, задачи, платежи, Google-файлы, история активности.",
        "Поиск по имени, компании, email, телефону и заметкам без учёта регистра.",
        "Фильтры по статусу, ответственному и архиву; пагинация.",
    ]),
    ("h2", "3.4. Сделки и заказы"),
    ("bullets", [
        "CRUD сделок: название, клиент (необязательно), проект, тип (сделка/заказ), сумма, валюта, этап, описание.",
        "Этапы: новая, переговоры, предложение, выиграна, проиграна, выполнена.",
        "Сделка может существовать без клиента; клиент привязывается и отвязывается.",
        "Заказ должен поддерживать позиции: товар, наименование, количество, цена, сумма.",
        "При изменении позиций сумма заказа пересчитывается.",
        "Выполнение заказа должно списывать товары со склада и фиксировать движения.",
        "Смена этапа должна логироваться и при необходимости уведомлять ответственного.",
    ]),
    ("h2", "3.5. Задачи и напоминания"),
    ("bullets", [
        "CRUD задач: заголовок, описание, клиент, сделка, проект, исполнитель, дедлайн, приоритет.",
        "Статусы: открыта, выполнена; поддержка повторного открытия.",
        "Фильтры: просроченные, сегодня, будущие, без срока, выполненные.",
        "Уведомление исполнителю при назначении и приближении дедлайна.",
        "Планировщик должен ежедневно проверять просроченные и близкие задачи.",
        "Задача может быть связана с клиентом, сделкой или только с проектом.",
    ]),
    ("h2", "3.6. Платежи и Robokassa"),
    ("bullets", [
        "CRUD платежей: проект, клиент, сделка, сумма, валюта, назначение, статус, способ.",
        "Статусы: ожидает, оплачен, ошибка, возврат, отменён.",
        "Генерация ссылки Robokassa с корректной подписью MD5 и тестовым режимом IsTest=1.",
        "Проверка подписи ResultURL с Password2 и идемпотентное обновление статуса.",
        "Ручная отметка оплаты для локального режима.",
        "При оплате создаётся доходная управленческая транзакция и уведомление.",
        "При возврате создаётся компенсирующая расходная транзакция.",
        "Ссылка на оплату и история статусов отображаются в карточке платежа.",
    ]),
    ("h2", "3.7. Склад и позиции заказов"),
    ("bullets", [
        "CRUD товаров: SKU, название, единица, цена продажи, себестоимость, остаток, минимальный остаток.",
        "Складские операции: приход, расход, корректировка; история движений.",
        "Контроль отрицательного остатка; запрет списания больше доступного количества.",
        "Расчёт стоимости склада по себестоимости.",
        "Список товаров с остатком ниже минимального.",
        "Позиции заказа связываются с товаром или вводятся вручную.",
        "Выполнение заказа создаёт расходные движения по позициям.",
    ]),
    ("h2", "3.8. Управленческий учёт"),
    ("bullets", [
        "CRUD доходов и расходов: проект, тип, категория, сумма, дата, описание, связь с платежом/сделкой.",
        "Автоматическое создание дохода при оплате платежа.",
        "Расчёт выручки, расходов и прибыли за период и по проекту.",
        "Фильтры по периоду, типу, категории и проекту.",
        "Экспорт транзакций в CSV и Google Sheets.",
        "Подтверждение: система не формирует налоговую и бухгалтерскую отчётность.",
    ]),
    ("h2", "3.9. Отчёты, выгрузка и расписание"),
    ("bullets", [
        "Типы отчётов: сводка CRM, продажи, финансы, склад, задачи.",
        "Генерация отчёта в Google Таблице с оформлением: заголовок, KPI, таблицы, итоги, диаграмма.",
        "AI-резюме через AITunnel; при недоступности — резервный текст без прерывания отчёта.",
        "CSV-выгрузка клиентов, сделок, задач, платежей, транзакций и склада.",
        "История отчётов со ссылками и статусом.",
        "Расписание: cron-выражение, проект, тип отчёта, получатели, каналы email/Telegram.",
        "Ручной запуск расписания и отображение следующего запуска.",
        "Ошибки генерации логируются и не блокируют следующие запуски.",
    ]),
    ("h2", "3.10. Уведомления"),
    ("bullets", [
        "Email через SMTP и Telegram через Bot API.",
        "Настройки пользователя: email, Telegram chat_id, включение каналов.",
        "События: назначение задачи, приближение дедлайна, смена этапа сделки, оплата, отчёт, тестовое сообщение.",
        "Надёжная доставка через outbox-таблицу: pending, sent, failed, skipped.",
        "Повторные попытки и журнал ошибок без раскрытия паролей и токенов.",
        "Администратор видит статус интеграций и может отправить тестовое сообщение.",
    ]),
    ("h2", "3.11. Google Drive, Docs, Sheets"),
    ("bullets", [
        "Сервисный аккаунт: чтение списка файлов, метаданных, скачивание, создание папок, загрузка, перемещение, переименование, удаление в корзину.",
        "OAuth2 личного аккаунта: вход, сохранение и обновление токена, создание Google Документов и Таблиц в заданной папке.",
        "Bootstrap: создание папки custom-CRM и выдача доступа сервисному аккаунту.",
        "Ссылки на созданные файлы сохраняются в CRM и отображаются в карточках.",
        "Ошибки Google API обрабатываются с понятными сообщениями; секреты не логируются.",
        "Точки входа: python -m app.google.service_account --list, python -m app.google.oauth_user --login, --create-test.",
    ]),
    ("h2", "3.12. Поиск"),
    ("bullets", [
        "Поиск по клиентам, сделкам и задачам в активном проекте.",
        "Регистронезависимый поиск, включая кириллицу.",
        "Фильтры по статусу, этапу, исполнителю, датам и архиву.",
        "Пагинация и сортировка.",
        "API-поиск и поиск в интерфейсе используют единый сервис.",
    ]),
    ("h2", "3.13. API"),
    ("bullets", [
        "REST API с JSON, версионированием /api и OpenAPI-документацией /docs.",
        "Аутентификация через сессию или Bearer-токен.",
        "Ролевые ограничения и фильтрация по проектам.",
        "Единый формат ошибок, коды 400/401/403/404/409/422/500.",
        "Пагинация, поиск, сортировка и фильтры.",
    ]),
    ("h2", "3.14. Дашборд"),
    ("bullets", [
        "KPI: клиенты, активные сделки, сумма воронки, выручка, расходы, прибыль.",
        "Воронка по этапам и задачи по срокам.",
        "Последние сделки, платежи и события.",
        "Товары с низким остатком.",
        "Быстрые действия: создать клиента, сделку, задачу, платёж.",
    ]),
    ("h2", "3.15. Администрирование и настройки"),
    ("bullets", [
        "Управление пользователями, ролями и проектами.",
        "Настройки Google, Robokassa, SMTP и Telegram.",
        "Проверка подключений и тестовые отправки.",
        "Просмотр журнала активности и системных логов.",
        "Резервное копирование и восстановление.",
    ]),
    ("h2", "3.16. Импорт и экспорт"),
    ("bullets", [
        "Экспорт CSV с UTF-8 BOM для Excel.",
        "Экспорт в Google Sheets.",
        "Импорт клиентов и товаров из CSV — после MVP, архитектурно предусмотрен.",
        "Массовые операции и выгрузка отчётов — через API и UI.",
    ]),

    ("h1", "4. Нефункциональные требования"),
    ("h2", "4.1. Надёжность"),
    ("bullets", [
        "Все операции с БД выполняются в транзакциях.",
        "Платежи и уведомления идемпотентны.",
        "Healthcheck /health проверяет приложение и БД.",
        "Ошибки интеграций не приводят к потере данных.",
        "Резервное копирование SQLite и PostgreSQL описано и автоматизировано командой.",
        "Время восстановления после сбоя — до 30 минут при наличии резервной копии.",
    ]),
    ("h2", "4.2. Производительность"),
    ("bullets", [
        "Время отклика типовой страницы — не более 2 секунд при локальной БД до 100 000 записей.",
        "Пагинация и индексы для списков.",
        "Фоновые отчёты и уведомления не блокируют HTTP-запросы.",
        "Кэширование тяжёлых агрегатов — при необходимости, без устаревания критичных данных.",
    ]),
    ("h2", "4.3. Масштабируемость"),
    ("bullets", [
        "SQLite по умолчанию; PostgreSQL через DATABASE_URL.",
        "Docker-образ и конфигурация без привязки к Windows.",
        "API-first архитектура допускает замену Jinja2-интерфейса на React.",
        "Планировщик рассчитан на один экземпляр; для нескольких экземпляров — внешний scheduler.",
    ]),
    ("h2", "4.4. Безопасность"),
    ("bullets", [
        "Argon2 для паролей, подписанные HttpOnly/SameSite cookie.",
        "CSRF-защита форм, параметризованные SQL-запросы.",
        "RBAC и проверка принадлежности к проекту.",
        "Секреты только в .env и secrets/, исключены из git.",
        "Логи без паролей, токенов и персональных секретов.",
        "Рекомендуется HTTPS reverse proxy при доступе вне localhost.",
    ]),
    ("h2", "4.5. Совместимость"),
    ("bullets", [
        "Windows 10/11 и Linux.",
        "Python 3.12.",
        "Docker Engine 24+ и Docker Compose v2+.",
        "Современные браузеры Chrome, Edge, Firefox, Safari.",
        "Экран от 1280 px; адаптивная верстка для планшетов.",
    ]),
    ("h2", "4.6. Локализация"),
    ("bullets", [
        "Русский интерфейс и сообщения об ошибках.",
        "Валюта RUB по умолчанию, поддержка иной валюты проекта.",
        "Часовой пояс Europe/Moscow по умолчанию, настраивается.",
        "Форматы дат ДД.ММ.ГГГГ и сумм с разделителями.",
    ]),
    ("h2", "4.7. Документирование"),
    ("bullets", [
        "README без Markdown-разметки, обновляется после каждого изменения.",
        "Техническое задание в PDF.",
        "Руководство по Google Cloud и OAuth2.",
        "Руководство администратора и инструкция по устранению неполадок.",
    ]),
    ("h2", "4.8. Тестирование"),
    ("bullets", [
        "pytest для БД, API, прав, поиска, платежей, склада, учёта и уведомлений.",
        "Моки Google API и SMTP/Telegram в автотестах.",
        "Ручной чек-лист UI и Docker.",
        "Минимальное покрытие критичных сервисов — 70%.",
    ]),
    ("h2", "4.9. Логирование и мониторинг"),
    ("bullets", [
        "Ротация logs/app.log.",
        "Уровни DEBUG/INFO/WARNING/ERROR.",
        "Healthcheck и статус интеграций.",
        "Журнал активности пользователей.",
    ]),
    ("h2", "4.10. Резервное копирование"),
    ("bullets", [
        "SQLite: копия файла data/crm.db с предварительным checkpoint WAL.",
        "PostgreSQL: pg_dump по расписанию.",
        "Хранение не менее 7 ежедневных копий.",
        "Проверка восстановления на тестовой БД.",
    ]),

    ("h1", "5. Архитектура"),
    ("h2", "5.1. Общая схема"),
    ("p", "Браузер взаимодействует с FastAPI. FastAPI отдаёт Jinja2-шаблоны и JSON API, работает с SQLAlchemy и БД, вызывает Google API, Robokassa, AITunnel, SMTP и Telegram. APScheduler выполняет фоновые задачи: обработку outbox-уведомлений, проверку дедлайнов и запуск отчётов по расписанию."),
    ("table", [
        ["Компонент", "Назначение"],
        ["FastAPI + Uvicorn", "HTTP-сервер, REST API, серверный рендеринг, зависимости и права."],
        ["Jinja2 + Alpine.js + JS", "Пользовательский интерфейс, таблицы, формы, модальные окна и интерактивные элементы."],
        ["SQLAlchemy 2.0", "Единый слой БД для SQLite и PostgreSQL, ORM-модели, транзакции."],
        ["APScheduler + croniter", "Напоминания, outbox-уведомления, расписание отчётов."],
        ["Google API", "Drive, Docs, Sheets; сервисный аккаунт и OAuth2 пользователя."],
        ["Robokassa", "Генерация ссылок и проверка ResultURL."],
        ["AITunnel", "AI-резюме отчётов с резервным текстом."],
        ["Docker Compose", "Запуск, монтирование кода, hot reload, PostgreSQL-профиль."],
    ], [4.0 * cm, 13.4 * cm]),
    ("h2", "5.2. Стек"),
    ("bullets", [
        "Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2.0, Pydantic 2, pydantic-settings.",
        "SQLite (по умолчанию) и PostgreSQL 16 (опционально).",
        "Jinja2, Alpine.js, Chart.js, минимальный JavaScript, собственный CSS в палитре Aillix.",
        "pwdlib[argon2], itsdangerous, python-multipart, email-validator.",
        "google-api-python-client, google-auth, google-auth-oauthlib.",
        "openai (AITunnel), httpx, smtplib, apscheduler, croniter.",
        "pytest, ruff.",
    ]),
    ("h2", "5.3. Структура проекта"),
    ("p", "app/main.py — точка входа; app/config.py — настройки; app/database.py — движок и сессии; app/models.py — ORM-модели; app/schemas.py — Pydantic-схемы; app/api/ — JSON API; app/web/ — UI-маршруты и шаблоны; app/services/ — бизнес-логика; app/google/ — интеграции Google; tests/ — автотесты; data/ — БД; secrets/ — ключи; docs/ — документация; Dockerfile, docker-compose.yml, start.bat."),
    ("h2", "5.4. Потоки данных"),
    ("numbered", [
        "Пользователь входит, получает сессию и активный проект.",
        "Форма UI проходит CSRF-проверку и вызывает сервис.",
        "Сервис проверяет права, выполняет операцию в транзакции и пишет журнал.",
        "При событии создаётся запись в outbox; фоновый обработчик отправляет email/Telegram.",
        "Отчёт собирает агрегаты, вызывает AITunnel, пишет Google Sheet и сохраняет ссылку.",
        "Планировщик проверяет расписания и дедлайны, создавая новые задания.",
    ]),
    ("h2", "5.5. Аутентификация и права"),
    ("p", "Сессия хранится в подписанной cookie. API принимает Bearer-токен. Проверка прав выполняется зависимостями FastAPI: require_user, require_admin, require_project_access. Администратор имеет доступ ко всем проектам; остальные — только к проектам, где состоят участниками."),
    ("h2", "5.6. Фоновые задачи"),
    ("p", "APScheduler запускается в lifespan приложения при SCHEDULER_ENABLED=true. Задачи открывают собственную сессию БД, обрабатывают outbox, дедлайны и расписания. Ошибки логируются и не останавливают приложение. В тестах планировщик отключён."),

    ("h1", "6. Модель данных"),
    ("h2", "6.1. Общие принципы"),
    ("bullets", [
        "Первичные ключи — целые автоинкрементные.",
        "Денежные поля — NUMERIC(12,2), валюта — строка ISO 4217.",
        "Даты — timezone-aware; API отдаёт ISO 8601.",
        "Мягкое удаление и архивирование вместо физического удаления там, где важна история.",
        "Внешние ключи с ON DELETE RESTRICT/SET NULL; каскад только для зависимых строк.",
        "Поле search_text хранит нормализованную строку для поиска без учёта регистра.",
    ]),
    ("h2", "6.2. Основные таблицы"),
    ("table", [
        ["Таблица", "Ключевые поля", "Назначение"],
        ["users", "id, email, password_hash, full_name, role, is_active, telegram_chat_id, notify_email, notify_telegram, created_at", "Пользователи и настройки уведомлений"],
        ["api_tokens", "id, user_id, name, token_hash, expires_at, last_used_at", "Bearer-токены API"],
        ["projects", "id, name, code, description, status, currency, owner_id, is_archived, created_at", "Проекты"],
        ["project_members", "project_id, user_id, role", "Участники проектов"],
        ["clients", "id, project_id, name, company, email, phone, status, source, notes, owner_id, is_archived, search_text", "Клиенты"],
        ["deals", "id, project_id, client_id NULL, kind, title, amount, currency, stage, description, owner_id, fulfilled_at, search_text", "Сделки и заказы"],
        ["order_items", "id, deal_id, product_id NULL, name, quantity, unit_price, total", "Позиции заказа"],
        ["tasks", "id, project_id, client_id NULL, deal_id NULL, title, description, due_at, priority, assigned_to_id, is_completed, completed_at, search_text", "Задачи"],
        ["payments", "id, project_id, client_id, deal_id, amount, currency, status, method, inv_id, robokassa_link, paid_at, created_at", "Платежи"],
        ["products", "id, project_id, sku, name, unit, price, cost, stock_qty, min_stock, is_active", "Товары"],
        ["stock_movements", "id, project_id, product_id, movement_type, quantity, unit_cost, reference, comment, created_by_id, created_at", "Движения склада"],
        ["transactions", "id, project_id, type, category, amount, currency, transaction_date, description, payment_id NULL, deal_id NULL, created_by_id", "Доходы и расходы"],
        ["reports", "id, project_id, report_type, period_from, period_to, spreadsheet_url, summary, created_by_id, created_at", "История отчётов"],
        ["report_schedules", "id, project_id, report_type, cron_expression, recipients_email, recipients_telegram, channels, is_active, last_run_at, next_run_at, last_error, created_by_id", "Расписание отчётов"],
        ["notifications", "id, user_id NULL, project_id NULL, channel, recipient, subject, body, status, attempts, error, dedupe_key UNIQUE, created_at, sent_at", "Outbox уведомлений"],
        ["google_files", "id, entity_type, entity_id, file_id, name, mime_type, web_url, created_at", "Ссылки на Google-файлы"],
        ["activity_log", "id, project_id, user_id, entity_type, entity_id, action, details, created_at", "Журнал действий"],
        ["app_settings", "key UNIQUE, value, updated_at", "Настройки, включая folder_id"],
    ], [3.2 * cm, 8.3 * cm, 5.9 * cm]),
    ("h2", "6.3. Статусы и этапы"),
    ("table", [
        ["Сущность", "Значения"],
        ["Клиент", "new, active, inactive, archived"],
        ["Сделка", "new, negotiation, proposal, won, lost, fulfilled"],
        ["Задача", "open, done (is_completed)"],
        ["Приоритет", "low, normal, high, urgent"],
        ["Платёж", "pending, paid, failed, refunded, canceled"],
        ["Складская операция", "in, out, adjust"],
        ["Транзакция", "income, expense"],
        ["Роль", "admin, manager, viewer"],
    ], [5.0 * cm, 12.4 * cm]),
    ("h2", "6.4. Индексы и ограничения"),
    ("bullets", [
        "Уникальные: users.email, projects.code, api_tokens.token_hash, notifications.dedupe_key.",
        "Индексы: clients(project_id, status), deals(project_id, stage), tasks(project_id, due_at, is_completed), payments(project_id, status), products(project_id, sku), transactions(project_id, transaction_date).",
        "Проверки: положительные суммы, неотрицательный остаток, допустимые статусы.",
        "Поиск: search_text + LIKE; для PostgreSQL допускается ILIKE.",
    ]),

    ("h1", "7. API"),
    ("h2", "7.1. Общие принципы"),
    ("bullets", [
        "Базовый путь /api; формат JSON; OpenAPI на /docs.",
        "Пагинация: page, per_page (по умолчанию 20, максимум 100).",
        "Сортировка: sort_by, sort_dir=asc|desc.",
        "Фильтры: project_id, q, status, stage, assigned_to, date_from, date_to.",
        "Ошибки: {detail, code, fields} с корректным HTTP-кодом.",
    ]),
    ("h2", "7.2. Аутентификация"),
    ("bullets", [
        "POST /api/auth/login — вход, установка сессии.",
        "POST /api/auth/logout — выход.",
        "GET /api/auth/me — текущий пользователь и доступные проекты.",
        "POST /api/auth/tokens — создать API-токен.",
        "DELETE /api/auth/tokens/{id} — отозвать токен.",
        "Bearer-токен передаётся в Authorization: Bearer <token>.",
    ]),
    ("h2", "7.3. Основные endpoints"),
    ("table", [
        ["Группа", "Endpoints"],
        ["Проекты", "GET/POST /api/projects; GET/PUT/DELETE /api/projects/{id}; GET/POST/DELETE /api/projects/{id}/members"],
        ["Клиенты", "GET/POST /api/clients; GET/PUT/DELETE /api/clients/{id}; POST /api/clients/{id}/archive; POST /api/clients/{id}/restore"],
        ["Сделки", "GET/POST /api/deals; GET/PUT/DELETE /api/deals/{id}; POST /api/deals/{id}/items; DELETE /api/deals/{id}/items/{item_id}; POST /api/deals/{id}/fulfill"],
        ["Задачи", "GET/POST /api/tasks; GET/PUT/DELETE /api/tasks/{id}; POST /api/tasks/{id}/complete; POST /api/tasks/{id}/reopen"],
        ["Платежи", "GET/POST /api/payments; GET/PUT /api/payments/{id}; POST /api/payments/{id}/mark-paid; POST /api/payments/{id}/refund; GET /api/payments/{id}/link"],
        ["Склад", "GET/POST /api/products; GET/PUT/DELETE /api/products/{id}; GET/POST /api/stock/movements; GET /api/stock/low"],
        ["Учёт", "GET/POST /api/transactions; GET/PUT/DELETE /api/transactions/{id}; GET /api/accounting/summary"],
        ["Отчёты", "POST /api/reports/generate; GET /api/reports; GET /api/reports/{id}; POST /api/reports/{id}/retry"],
        ["Расписания", "GET/POST /api/report-schedules; GET/PUT/DELETE /api/report-schedules/{id}; POST /api/report-schedules/{id}/run"],
        ["Уведомления", "GET /api/notifications; POST /api/notifications/test; GET /api/notifications/status"],
        ["Google", "GET /api/google/status; GET /api/google/files; POST /api/google/docs; POST /api/google/sheets; POST /api/google/bootstrap"],
        ["Поиск", "GET /api/search?q="],
        ["Админ", "GET/POST /api/users; GET/PUT/DELETE /api/users/{id}; GET /api/activity"],
        ["Система", "GET /health; GET /api/system/info"],
    ], [3.4 * cm, 14.0 * cm]),

    ("h1", "8. Развёртывание"),
    ("h2", "8.1. Варианты запуска"),
    ("bullets", [
        "SQLite: docker compose up -d --build; база в data/crm.db; подходит для одного пользователя и локальной работы.",
        "PostgreSQL: docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build; DATABASE_URL указывает на сервис db.",
        "Локальный Python: .venv + pip install -r requirements.txt + uvicorn.",
        "start.bat автоматизирует остановку старых процессов, очистку кэша, сборку, запуск, healthcheck и открытие браузера.",
    ]),
    ("h2", "8.2. Docker и hot reload"),
    ("bullets", [
        "Код монтируется в /app.",
        "Uvicorn запускается с --reload и --reload-dir /app.",
        "WATCHFILES_FORCE_POLLING=true для Windows bind mounts.",
        "Изменения Python перезапускают сервер; шаблоны и CSS обновляются без пересборки.",
        "Порт 8000 привязан к 127.0.0.1.",
    ]),
    ("h2", "8.3. Переменные окружения"),
    ("p", "Основные переменные: APP_ENV, SECRET_KEY, DATABASE_URL, ADMIN_EMAIL, ADMIN_PASSWORD, GOOGLE_SERVICE_ACCOUNT_FILE, GOOGLE_OAUTH_CLIENT_SECRET_FILE, GOOGLE_OAUTH_TOKEN_FILE, GOOGLE_DRIVE_FOLDER_ID, REPORT_SPREADSHEET_ID, ROBOKASSA_MERCHANT_LOGIN, ROBOKASSA_PASSWORD1, ROBOKASSA_PASSWORD2, ROBOKASSA_TEST_MODE, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, TELEGRAM_BOT_TOKEN, AITUNNEL_API_KEY, SCHEDULER_ENABLED, TIMEZONE. Полный список — в .env.example."),
    ("h2", "8.4. Google Cloud"),
    ("numbered", [
        "Включить Google Drive API, Google Docs API, Google Sheets API.",
        "Создать сервисный аккаунт и скачать JSON-ключ.",
        "Создать OAuth-клиент типа Desktop и скачать client_secret JSON.",
        "Добавить redirect URI http://localhost:8765/.",
        "Добавить тестового пользователя в OAuth consent screen.",
        "Выдать сервисному аккаунту доступ Editor к папке и таблице отчётов.",
        "Выполнить bootstrap папки и вход OAuth2.",
    ]),
    ("h2", "8.5. Robokassa"),
    ("bullets", [
        "Тестовый режим: ROBOKASSA_TEST_MODE=true, IsTest=1.",
        "Пароль 1 — для ссылки, пароль 2 — для ResultURL.",
        "ResultURL должен быть доступен из интернета; локально используйте туннель или ручную отметку.",
        "При отсутствии реквизитов кнопка ссылки отключена, ручная оплата доступна.",
    ]),
    ("h2", "8.6. Уведомления"),
    ("bullets", [
        "SMTP: host, port, user, password, TLS, from.",
        "Telegram: bot token и chat_id пользователя.",
        "При отсутствии настроек уведомление помечается skipped, приложение продолжает работу.",
        "Тестовая отправка доступна в настройках.",
    ]),
    ("h2", "8.7. Резервное копирование"),
    ("bullets", [
        "SQLite: scripts/backup_db.py создаёт копию с checkpoint WAL.",
        "PostgreSQL: pg_dump через docker compose exec db.",
        "Копии хранятся в data/backups с датой и временем.",
        "Восстановление описано в docs/admin-guide.txt.",
    ]),

    ("h1", "9. Тестирование и приёмка"),
    ("h2", "9.1. Виды тестов"),
    ("bullets", [
        "Модульные: БД, поиск, права, платежи, склад, учёт, уведомления.",
        "Интеграционные: API через TestClient, сессии, CSRF, роли.",
        "Моки: Google API, SMTP, Telegram, AITunnel.",
        "Ручные: UI, Docker, hot reload, OAuth2, Robokassa-ссылка.",
    ]),
    ("h2", "9.2. Чек-лист приёмки"),
    ("numbered", [
        "start.bat останавливает старые процессы, чистит кэш, собирает и запускает приложение.",
        "Приложение доступно на http://127.0.0.1:8000, /health отвечает 200.",
        "Администратор входит, создаёт проект, пользователя и участника проекта.",
        "Менеджер видит только свои проекты и не может открыть чужой проект.",
        "Клиент, сделка, заказ, задача и платёж создаются, редактируются и удаляются согласно правам.",
        "Поиск по русским именам работает без учёта регистра.",
        "Заказ с позициями списывает товары со склада и создаёт движения.",
        "Оплата платежа создаёт доходную транзакцию; возврат создаёт расходную.",
        "Robokassa-ссылка формируется с корректной подписью; ResultURL проверяет подпись.",
        "Отчёт генерируется в Google Таблицу, AI-резюме или резервный текст присутствует.",
        "Расписание отчёта запускается вручную и по cron, создаёт уведомления.",
        "Email и Telegram-уведомления работают при заданных настройках; без них — skipped.",
        "Google Drive показывает файлы папки; OAuth2 создаёт Документ и Таблицу от имени пользователя.",
        "CSV открывается в Excel без искажения кодировки.",
        "Секреты отсутствуют в git; README без Markdown соответствует фактическим командам.",
        "pytest проходит; Docker-образ собирается; финальный commit/push выполнен.",
    ]),
    ("h2", "9.3. Definition of Done"),
    ("bullets", [
        "Все функции раздела 3 реализованы и проверены.",
        "Критичные ошибки отсутствуют; известные ограничения описаны.",
        "README, ТЗ, Google-инструкция и руководство администратора обновлены.",
        "Миграции/инициализация БД воспроизводимы на чистой машине.",
        "Секреты не попадают в репозиторий.",
        "Финальный commit и push выполнены.",
    ]),

    ("h1", "10. Этапы и сроки"),
    ("table", [
        ["Этап", "Содержание", "Оценка"],
        ["0", "Каркас, .env, secrets, Docker, git, README, ТЗ", "4–5 ч"],
        ["1", "Google Drive сервисного аккаунта + CLI", "3–4 ч"],
        ["2", "OAuth2, Docs/Sheets, bootstrap папки", "5–6 ч"],
        ["3", "SQLAlchemy-модели, БД, миграции, seed, тесты", "5–6 ч"],
        ["4", "Auth, пользователи, роли, проекты, API", "6–8 ч"],
        ["5", "Клиенты, сделки, задачи, поиск, API", "6–8 ч"],
        ["6", "Платежи, Robokassa, склад, учёт", "6–8 ч"],
        ["7", "Отчёты, Google Sheets, AI, расписания, уведомления", "8–10 ч"],
        ["8", "UI, палитра Aillix, дашборд, формы", "10–12 ч"],
        ["9", "Docker, start.bat, тесты, README, git", "6–8 ч"],
    ], [1.4 * cm, 12.6 * cm, 3.4 * cm]),
    ("p", "Итого: 59–75 часов. Ориентировочный срок — 8–10 рабочих дней при последовательной реализации. Возможна поэтапная сдача: сначала ядро CRM, затем Google/Robokassa, затем отчёты и уведомления."),

    ("h1", "11. Ограничения и допущения"),
    ("bullets", [
        "Заказчик предоставляет доступы к Google Cloud, Robokassa, SMTP и Telegram.",
        "Первичная настройка OAuth2 требует ручного подтверждения в браузере.",
        "Внешние API могут быть недоступны; система должна деградировать без потери данных.",
        "Юридическая и налоговая отчётность не формируется.",
        "При использовании PostgreSQL требуется отдельный сервер или контейнер.",
        "Планировщик не гарантирует запуск при остановленном приложении.",
        "Дизайн следует палитре Aillix, но не копирует логотипы и фирменные материалы сайта.",
    ]),

    ("h1", "12. Риски"),
    ("table", [
        ["Риск", "Вероятность", "Митигация"],
        ["OAuth2 redirect и токен в Docker", "Средняя", "Проброс 8765, инструкция, повторный вход, Production-режим OAuth"],
        ["Сервисный аккаунт без квоты Drive", "Высокая", "Создание файлов через OAuth2, сервисный аккаунт — чтение и работа в расшаренной папке"],
        ["Нет доступа к таблице/папке", "Средняя", "Проверка прав Editor, bootstrap, диагностика 403"],
        ["Windows hot reload не видит файлы", "Средняя", "WATCHFILES_FORCE_POLLING=true, polling"],
        ["SQLite на bind mount", "Средняя", "WAL, busy_timeout, named volume при проблемах"],
        ["Секреты в git", "Высокая", ".gitignore, проверка перед commit, секреты только в secrets/.env"],
        ["Сложность полного функционала", "Высокая", "Поэтапная сдача, тесты, приоритет MVP"],
        ["Сбои SMTP/Telegram", "Средняя", "Outbox, повторные попытки, статус skipped"],
        ["Дублирование планировщика", "Низкая", "Один экземпляр приложения, документация"],
    ], [5.4 * cm, 2.6 * cm, 9.4 * cm]),

    ("h1", "13. Приложения"),
    ("h2", "13.1. Переменные окружения"),
    ("table", [
        ["Переменная", "Назначение"],
        ["SECRET_KEY", "Подпись сессий и CSRF"],
        ["DATABASE_URL", "sqlite:///./data/crm.db или postgresql+psycopg://..."],
        ["ADMIN_EMAIL / ADMIN_PASSWORD", "Первичный администратор"],
        ["GOOGLE_SERVICE_ACCOUNT_FILE", "Путь к JSON сервисного аккаунта"],
        ["GOOGLE_OAUTH_CLIENT_SECRET_FILE", "Путь к client_secret JSON"],
        ["GOOGLE_OAUTH_TOKEN_FILE", "Путь к token.json"],
        ["GOOGLE_DRIVE_FOLDER_ID", "Папка Google Drive"],
        ["REPORT_SPREADSHEET_ID", "Рабочая Google Таблица отчётов"],
        ["ROBOKASSA_MERCHANT_LOGIN / PASSWORD1 / PASSWORD2", "Реквизиты Robokassa"],
        ["ROBOKASSA_TEST_MODE", "true/false"],
        ["SMTP_HOST / PORT / USER / PASSWORD / FROM", "Почта"],
        ["TELEGRAM_BOT_TOKEN", "Telegram Bot API"],
        ["AITUNNEL_API_KEY / BASE_URL / MODEL", "AI-резюме"],
        ["SCHEDULER_ENABLED", "Включение фоновых задач"],
        ["TIMEZONE", "Europe/Moscow"],
    ], [7.2 * cm, 10.2 * cm]),
    ("h2", "13.2. Примеры cron"),
    ("bullets", [
        "Ежедневно в 09:00: 0 9 * * *",
        "По понедельникам в 10:00: 0 10 * * 1",
        "Первое число месяца в 08:30: 30 8 1 * *",
        "Каждые 6 часов: 0 */6 * * *",
    ]),
    ("h2", "13.3. Репозиторий"),
    ("p", "https://github.com/markmus11012020-max/custom-CRM.git"),
    ("note", "Документ считается утверждённым после подтверждения заказчиком. Изменения объёма оформляются новой версией ТЗ."),
]


def wrap_text(text: str, width: int = 110) -> str:
    return "\n".join(textwrap.wrap(text, width=width)) if text else ""


def build_story() -> list:
    story: list = []
    for block in BLOCKS:
        kind = block[0]
        if kind == "title":
            story.append(Spacer(1, 4.2 * cm))
            story.append(p(block[1], "Title"))
        elif kind == "subtitle":
            story.append(p(block[1], "Subtitle"))
        elif kind == "meta":
            rows = [[label, value] for label, value in block[1]]
            table = Table(
                [[Paragraph(escape(a), STYLES["Small"]), Paragraph(escape(b), STYLES["Small"])] for a, b in rows],
                colWidths=[4.2 * cm, 11.0 * cm],
                hAlign="CENTER",
            )
            table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(table)
        elif kind == "note":
            story.append(Paragraph(escape(block[1]), STYLES["Note"]))
            story.append(Spacer(1, 0.2 * cm))
        elif kind == "pagebreak":
            story.append(PageBreak())
        elif kind == "h1":
            story.append(p(block[1], "H1"))
        elif kind == "h2":
            story.append(p(block[1], "H2"))
        elif kind == "h3":
            story.append(p(block[1], "H3"))
        elif kind == "p":
            story.append(p(block[1], "Body"))
        elif kind == "bullets":
            story.extend(bullets(block[1]))
            story.append(Spacer(1, 0.15 * cm))
        elif kind == "numbered":
            story.extend(numbered(block[1]))
            story.append(Spacer(1, 0.15 * cm))
        elif kind == "table":
            widths = block[2] if len(block) > 2 else None
            story.append(make_table(block[1], widths))
            story.append(Spacer(1, 0.3 * cm))
        elif kind == "toc":
            toc = TableOfContents()
            toc.levelStyles = [STYLES["TOC0"], STYLES["TOC1"]]
            story.append(toc)
        else:
            raise ValueError(f"Неизвестный блок: {kind}")
    return story


def write_plain_text() -> None:
    lines: list[str] = []
    for block in BLOCKS:
        kind = block[0]
        if kind == "title":
            lines.append(block[1].upper())
            lines.append("=" * len(block[1]))
        elif kind == "subtitle":
            lines.append(block[1])
            lines.append("")
        elif kind == "meta":
            for label, value in block[1]:
                lines.append(f"{label}: {value}")
            lines.append("")
        elif kind == "note":
            lines.append(wrap_text(block[1]))
            lines.append("")
        elif kind == "pagebreak":
            lines.append("")
            lines.append("")
        elif kind == "h1":
            lines.append("")
            lines.append(block[1].upper())
            lines.append("-" * min(len(block[1]), 100))
        elif kind == "h2":
            lines.append("")
            lines.append(block[1])
            lines.append("~" * min(len(block[1]), 100))
        elif kind == "h3":
            lines.append("")
            lines.append(block[1])
        elif kind == "p":
            lines.append(wrap_text(block[1]))
            lines.append("")
        elif kind == "bullets":
            for item in block[1]:
                lines.append("- " + wrap_text(item, 105))
            lines.append("")
        elif kind == "numbered":
            for index, item in enumerate(block[1], 1):
                lines.append(f"{index}. " + wrap_text(item, 105))
            lines.append("")
        elif kind == "table":
            for row in block[1]:
                lines.append(" | ".join(str(cell) for cell in row))
            lines.append("")
        elif kind == "toc":
            lines.append("Содержание формируется автоматически в PDF-версии.")
            lines.append("")
    TXT_PATH.parent.mkdir(parents=True, exist_ok=True)
    TXT_PATH.write_text("\n".join(lines), encoding="utf-8-sig")


def main() -> None:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    pdfmetrics.registerFont(TTFont("Arial", FONT_REGULAR))
    pdfmetrics.registerFont(TTFont("Arial-Bold", FONT_BOLD))
    pdfmetrics.registerFont(TTFont("Consolas", FONT_MONO))
    pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial", boldItalic="Arial-Bold")

    TXT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_plain_text()

    doc = TechSpecDoc(
        str(PDF_PATH),
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.6 * cm,
        title="Техническое задание Custom-CRM",
        author="Custom-CRM",
        subject="Универсальная мини-CRM",
    )
    story = build_story()
    doc.multiBuild(story)
    print(f"PDF: {PDF_PATH}")
    print(f"TXT: {TXT_PATH}")


if __name__ == "__main__":
    main()
