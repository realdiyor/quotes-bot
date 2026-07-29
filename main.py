"""
Автопостинг ИИ-цитат в Telegram-канал.
Запускается через GitHub Actions по расписанию (см. .github/workflows/post.yml)

Нужны 3 переменные окружения (задаются как GitHub Secrets):
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHANNEL_ID   (например: @my_quotes_channel  или  -1001234567890)
- GEMINI_API_KEY
"""

import os
import json
import random
import requests
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# НАСТРОЙКИ ВАЙБА — редактируй этот блок, чтобы менять стиль канала
# ---------------------------------------------------------------------------

# Референсы, которые задают тон (можно менять/добавлять свои)
REFERENCE_EXAMPLES = [
    "girls do all that fbi research just to cry and stay",
    "she texted you goodnight just to text another mf \"i cant sleep\". stay woke",
    "she ghosted you? cool. now she just another follower watching you win.",
    "when you post her on your story, but shes the only one who can view it",
    "i promised i could change, i never promised i would",
    "you lost the bih, but you saved your future. you won",
    "flirt with many dont love any",
    "vision so bad i almost saw something in her",
    "a good man should pay your bills and not care about past. and that man is your father, not me",
    "just checked my horoscope it says im supposed to give you backshots today",
    "dont tell me \"we forever\" and then leave when i cheat",
    "the longer she takes to reply the cuter her friends gets",
    "calling me yo ex is wild i been single all my life",
    "text her \"get dressed\" and never pull up",
    "you gotta treat her like a rental. enjoy it, return it, and dont catch feelings",
]

SYSTEM_PROMPT = """Ты — автор популярного телеграм-канала с цитатами в стиле твиттер-постов
(жанр: циничные, дерзкие, self-aware шутки про отношения, отношения парень/девушка,
"игра", независимость, ирония над романтикой). Тон уверенный, немного дерзкий,
с юмором, без пошлости и без оскорблений конкретных людей.

Правила формата (СТРОГО):
- Только на русском языке.
- Одна короткая мысль. Максимум 1-2 предложения.
- БЕЗ восклицательных знаков.
- БЕЗ хэштегов, БЕЗ эмодзи, БЕЗ кавычек вокруг всего текста.
- БЕЗ вступлений и пояснений — сразу готовый текст поста.
- Без пафоса и без "продающих" фраз.
- Пиши как реальный твит: разговорно, живо, с лёгким сленгом, но грамотно.
- Не используй мат.

Вот примеры вайба (на английском — только для ощущения стиля и структуры шутки,
НЕ переводи их дословно, придумывай новые мысли в этом же духе):
{examples}

Уже опубликованные посты (НЕ повторяй их и не пиши слишком похожие по смыслу):
{history}

Напиши ОДНУ новую цитату на русском в этом вайбе. В ответе — только сам текст поста,
ничего больше."""

MODEL = "gemini-3.1-flash-lite"
HISTORY_LIMIT_IN_PROMPT = 25   # сколько последних постов показываем ИИ, чтобы не повторялся
MAX_HISTORY_STORED = 300       # сколько храним в файле максимум

# ---------------------------------------------------------------------------

HISTORY_FILE = os.path.join(os.path.dirname(__file__), "quotes_history.json")


def load_history() -> list[dict]:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(history: list[dict]) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-MAX_HISTORY_STORED:], f, ensure_ascii=False, indent=2)


def build_prompt(history: list[dict]) -> str:
    recent_texts = [h["text"] for h in history[-HISTORY_LIMIT_IN_PROMPT:]]
    examples_block = "\n".join(f"- {ex}" for ex in random.sample(
        REFERENCE_EXAMPLES, k=min(6, len(REFERENCE_EXAMPLES))
    ))
    history_block = "\n".join(f"- {t}" for t in recent_texts) or "(пока пусто)"
    return SYSTEM_PROMPT.format(examples=examples_block, history=history_block)


def generate_quote(history: list[dict]) -> str:
    api_key = os.environ["GEMINI_API_KEY"]
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": build_prompt(history)}]}],
        "generationConfig": {
            "temperature": 1.15,
            "maxOutputTokens": 120,
        },
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Не удалось разобрать ответ Gemini: {data}") from e

    # На случай, если модель всё же обернула текст в кавычки
    text = text.strip().strip('"').strip("«»").strip()
    return text


def post_to_telegram(text: str) -> None:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHANNEL_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Ошибка Telegram API: {resp.status_code} {resp.text}")


def main() -> None:
    history = load_history()

    # На случай неудачной генерации — пробуем до 3 раз
    last_error = None
    for attempt in range(3):
        try:
            quote = generate_quote(history)
            if quote and len(quote) > 3:
                break
        except Exception as e:  # noqa: BLE001
            last_error = e
            quote = None
    else:
        raise RuntimeError(f"Не получилось сгенерировать цитату: {last_error}")

    post_to_telegram(quote)

    history.append({
        "text": quote,
        "date": datetime.now(timezone.utc).isoformat(),
    })
    save_history(history)
    print(f"Опубликовано: {quote}")


if __name__ == "__main__":
    main()
