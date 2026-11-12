"""AI-резюме отчётов через AITunnel с резервным текстом."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from app.config import Settings, get_logger

LOGGER = get_logger("ai")

SYSTEM_PROMPT = (
    "Ты — опытный бизнес-аналитик. Пиши на русском языке деловым стилем. "
    "Сформулируй вывод объёмом 5–7 предложений. Не используй markdown, списки, "
    "заголовки и эмодзи. Используй только переданные цифры. Структура: динамика, "
    "ключевой драйвер, риск, конкретная рекомендация."
)


@dataclass
class AIResult:
    text: str
    used_fallback: bool = False
    error: str | None = None


class AITunnelClient:
    def __init__(self, settings: Settings) -> None:
        self.api_key = settings.aitunnel_api_key.strip()
        self.base_url = settings.aitunnel_base_url.strip().rstrip("/")
        self.model = settings.aitunnel_model.strip()
        self.timeout = settings.ai_timeout
        self.retries = max(0, settings.ai_retries)

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def generate_summary(self, context: dict[str, Any]) -> AIResult:
        if not self.configured:
            return AIResult(
                text=self.fallback_summary(context),
                used_fallback=True,
                error="AITunnel не настроен",
            )
        system_prompt = SYSTEM_PROMPT
        user_prompt = (
            "Данные CRM в JSON:\n"
            + json.dumps(context, ensure_ascii=False, indent=2, default=str)
            + "\n\nНапиши аналитический вывод: динамика, ключевой драйвер, риск и рекомендация."
        )
        last_error = ""
        for attempt in range(self.retries + 1):
            try:
                text = self._call(system_prompt, user_prompt)
                cleaned = self._sanitize(text)
                if cleaned:
                    return AIResult(text=cleaned)
                last_error = "Пустой ответ модели"
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                LOGGER.warning(
                    "AITunnel: попытка %s из %s не удалась: %s",
                    attempt + 1,
                    self.retries + 1,
                    last_error,
                )
                if attempt < self.retries:
                    time.sleep(2**attempt)
        return AIResult(
            text=self.fallback_summary(context),
            used_fallback=True,
            error=last_error,
        )

    def _call(self, system_prompt: str, user_prompt: str) -> str:
        from openai import OpenAI

        client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=0,
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=1400,
        )
        if not response.choices:
            raise RuntimeError("Провайдер не вернул варианты ответа")
        return response.choices[0].message.content or ""

    @staticmethod
    def _sanitize(text: str) -> str:
        value = (text or "").strip()
        value = re.sub(r"`{1,3}", "", value)
        value = re.sub(r"\*\*(.+?)\*\*", r"\1", value)
        value = re.sub(r"^#{1,6}\s*", "", value, flags=re.MULTILINE)
        value = re.sub(r"^\s*[-*•]\s+", "", value, flags=re.MULTILINE)
        value = re.sub(r"\s+", " ", value).strip()
        if len(value) > 1500:
            value = value[:1500].rsplit(".", 1)[0] + "."
        if value and value[-1] not in ".!?":
            value += "."
        return value

    @staticmethod
    def fallback_summary(context: dict[str, Any]) -> str:
        project = context.get("project", "проект")
        period = context.get("period", "выбранный период")
        kpis = context.get("kpis", []) or []
        parts = [f"За период {period} по проекту «{project}» сформирован отчёт."]
        if kpis:
            parts.append("Ключевые показатели: " + "; ".join(
                f"{item.get('name', '')} — {item.get('value', '')}" for item in kpis[:5]
            ) + ".")
        income = context.get("income")
        expense = context.get("expense")
        if income is not None and expense is not None:
            parts.append(f"Доходы составили {income}, расходы — {expense}.")
        parts.append(
            "Рекомендуется проверить задачи с приближающимся сроком, дебиторскую "
            "задолженность и товары с остатком ниже минимального."
        )
        return " ".join(parts)
