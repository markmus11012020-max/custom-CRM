CUSTOM-CRM
Универсальная мини-CRM для локального бизнеса

НАЗНАЧЕНИЕ

Custom-CRM — веб-приложение для управления клиентами, проектами, сделками,
заказами, задачами, платежами, складскими остатками, управленческим учётом
и отчётами. Работает локально через Docker или на сервере с PostgreSQL.

Документация проекта:
  ТехЗадание.pdf — техническое задание;
  docs/technical-spec.txt — текстовая версия ТЗ;
  docs/google-setup.txt — настройка Google;
  docs/admin-guide.txt — руководство администратора.

ВОЗМОЖНОСТИ

1. Многопользовательский режим: администратор, менеджер, наблюдатель.
2. Несколько проектов с изоляцией клиентов, сделок, задач и финансов.
3. Клиенты: CRUD, статусы, архив, ответственные, история, поиск.
4. Сделки и заказы: этапы, суммы, позиции, выполнение, списание со склада.
5. Задачи: сроки, приоритеты, исполнители, фильтры, напоминания.
6. Платежи: ручные счета и Robokassa в тестовом режиме, возвраты.
7. Склад: товары, приход, расход, корректировка, минимальные остатки.
8. Управленческий учёт: доходы, расходы, прибыль, экспорт.
9. Отчёты: Google Таблицы, AI-резюме, CSV, история, cron-расписание.
10. Уведомления: email SMTP и Telegram Bot API через outbox.
11. Google Drive: сервисный аккаунт и OAuth2 личного аккаунта.
12. REST API с OpenAPI, сессиями и Bearer-токенами.
13. Docker Compose, горячая перезагрузка, SQLite или PostgreSQL.

СТЕК

Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2.0, Pydantic 2,
Jinja2, Alpine.js, Chart.js, APScheduler, croniter,
Google Drive/Docs/Sheets API, AITunnel, SQLite, PostgreSQL, Docker.

СТРУКТУРА

app/main.py                 точка входа FastAPI
app/config.py               настройки из .env и логирование
app/database.py             движок БД, сессии, инициализация, seed
app/models.py               ORM-модели
app/schemas.py              Pydantic-схемы
app/security.py             Argon2, API-токены, CSRF
app/api/                    JSON API
app/services/               бизнес-логика, платежи, склад, отчёты, уведомления
app/google/                 Google Drive, Docs, Sheets, OAuth2
app/web/                    маршруты, шаблоны, CSS, JS
tests/                      pytest
data/                       SQLite и резервные копии
secrets/                    JSON-ключи и token.json
docs/                       документация
Dockerfile, docker-compose.yml, docker-compose.postgres.yml
start.bat, stop.bat, requirements.txt, .env, .env.example

ТРЕБОВАНИЯ

Windows 10/11 или Linux.
Python 3.12 для локального запуска.
Docker Engine и Docker Compose для контейнерного запуска.
Доступ в интернет для Google API, AITunnel, SMTP и Telegram.

БЫСТРЫЙ СТАРТ

1. Проверьте .env. Он создан как дубль .env.example и содержит локальные
   значения. Смените ADMIN_PASSWORD и SECRET_KEY перед использованием.
2. Запустите start.bat.
   Скрипт останавливает старые процессы, чистит Python-кэш, собирает
   окружение, запускает контейнер, ждёт healthcheck и открывает браузер.
3. Откройте http://127.0.0.1:8000
4. Войдите с email и паролем из .env. По умолчанию:
   admin@example.com / ChangeMe123!
5. Смените пароль в разделе Профиль.

Запуск с PostgreSQL:
  start.bat postgres

Остановка:
  stop.bat

Локальный запуск без Docker:
  python -m venv .venv
  .venv\Scripts\activate
  pip install -r requirements.txt
  uvicorn app.main:app --reload

ПЕРВЫЙ ПОЛЬЗОВАТЕЛЬ

При первом старте создаётся администратор из переменных ADMIN_EMAIL,
ADMIN_PASSWORD, ADMIN_NAME. Также создаётся проект "Основной проект".
Если SEED_DEMO=true и база пуста, добавляются демонстрационные клиенты,
сделки, задачи, товары, платёж и финансовые операции.

GOOGLE

Сервисный аккаунт:
  secrets/service_account.json
  Используется для чтения Google Drive и записи отчётов в таблицу.

OAuth2 личного аккаунта:
  secrets/client_secret.json
  token.json создаётся после входа.
  Команда входа:
    python -m app.google.oauth_user --login
  Без автоматического открытия браузера:
    python -m app.google.oauth_user --login --no-browser
  Проверка статуса:
    python -m app.google.oauth_user --status
  Создание тестовых Документа и Таблицы:
    python -m app.google.oauth_user --create-test

Создание рабочей папки и выдача доступа сервисному аккаунту:
  python -m app.google.bootstrap --folder custom-CRM

Проверка файлов через сервисный аккаунт:
  python -m app.google.service_account --list

В Google Cloud включите:
  Google Drive API;
  Google Docs API;
  Google Sheets API;
  OAuth consent screen;
  redirect URI http://localhost:8765/;
  доступ сервисного аккаунта к папке и таблице отчётов.

Если OAuth2 запускается в Docker, пробросьте порт 8765:
  docker compose run --rm -p 8765:8765 app python -m app.google.oauth_user --login

ROBOKASSA

Параметры задаются в .env:
  ROBOKASSA_MERCHANT_LOGIN
  ROBOKASSA_PASSWORD1
  ROBOKASSA_PASSWORD2
  ROBOKASSA_TEST_MODE=true
  ROBOKASSA_RESULT_URL
  ROBOKASSA_SUCCESS_URL
  ROBOKASSA_FAIL_URL

Ссылка формируется с подписью MD5(MerchantLogin:OutSum:InvId:Password1).
ResultURL проверяет MD5(OutSum:InvId:Password2). Для локальной проверки
используйте тестовые реквизиты или ручную отметку оплаты. Реальный
ResultURL должен быть доступен из интернета.

УВЕДОМЛЕНИЯ

Email:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TLS.

Telegram:
  TELEGRAM_BOT_TOKEN и Telegram chat_id пользователя в профиле.

Уведомления складываются в таблицу notifications и отправляются
планировщиком. Если канал не настроен, запись получает статус skipped.

ПЛАНИРОВЩИК

Планировщик запускается при SCHEDULER_ENABLED=true и выполняет:
  обработку outbox-уведомлений;
  проверку задач с дедлайном;
  запуск отчётов по cron-расписанию.

Примеры cron:
  0 9 * * * — ежедневно в 09:00;
  0 10 * * 1 — по понедельникам в 10:00;
  30 8 1 * * — первого числа месяца в 08:30.

ПЛАНИРОВЩИК РАССЧИТАН НА ОДИН ЭКЗЕМПЛЯР ПРИЛОЖЕНИЯ.

POSTGRESQL

PostgreSQL подключается через DATABASE_URL:
  postgresql+psycopg://crm:crm@db:5432/crm

Запуск:
  docker compose -f docker-compose.yml -f docker-compose.postgres.yml up -d --build
или
  start.bat postgres

Данные PostgreSQL хранятся в volume pgdata. Для резервной копии:
  docker compose exec db pg_dump -U crm crm > backup.sql

API

Базовый путь: /api
Документация: /docs и /openapi.json
Аутентификация: сессия или Authorization: Bearer <token>
Токены создаются в профиле пользователя.

Основные группы:
  /api/auth
  /api/projects
  /api/clients
  /api/deals
  /api/tasks
  /api/payments
  /api/products
  /api/stock
  /api/transactions
  /api/reports
  /api/report-schedules
  /api/google
  /api/search
  /api/users
  /api/activity
  /health

ТЕСТЫ

  pytest
  pytest --cov=app

Проверяются БД, API, права, поиск, платежи, склад, учёт, отчёты и уведомления.
Внешние Google/SMTP/Telegram вызовы в тестах не выполняются.

ДИАГНОСТИКА

Healthcheck:
  http://127.0.0.1:8000/health

Логи:
  logs/app.log

Если приложение не стартует:
  проверьте .env;
  проверьте занятость порта 8000;
  выполните stop.bat, затем start.bat;
  проверьте Docker: docker compose logs app.

Если Google возвращает 403:
  проверьте доступ сервисного аккаунта к папке и таблице с ролью Editor;
  включите Drive/Docs/Sheets API;
  проверьте OAuth redirect URI.

Если OAuth2 возвращает ошибку:
  выполните python -m app.google.oauth_user --status;
  повторите вход;
  при необходимости переведите OAuth-приложение из Testing в Production.

БЕЗОПАСНОСТЬ

Пароли хранятся в виде Argon2-хешей.
Сессии подписаны, cookie HttpOnly и SameSite=Lax.
Формы защищены CSRF-токеном.
API использует сессии или Bearer-токены.
Секреты находятся в .env и secrets/ и исключены из git.
Не публикуйте приложение в интернет без HTTPS reverse proxy.
Для локального использования порт привязан к 127.0.0.1.

РЕЗЕРВНОЕ КОПИРОВАНИЕ

SQLite:
  кнопка "Резервная копия БД" в настройках администратора
  или python -c "from app.database import Database; print(Database().backup())"

PostgreSQL:
  docker compose exec db pg_dump -U crm crm > backup.sql

Храните не менее 7 ежедневных копий и проверяйте восстановление.

РЕПОЗИТОРИЙ

https://github.com/markmus11012020-max/custom-CRM.git

ЛИЦЕНЗИЯ

Проект предназначен для внутреннего использования. ПО поставляется "как есть".
