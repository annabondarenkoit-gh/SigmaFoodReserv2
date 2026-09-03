"""
Парсинг PDF-меню через Google Gemini API (TC-01).

Вимоги:
- Витягти страви Сніданку, Обіду, Вечері.
- Розділ «Полуденок» ПОВНІСТЮ ігнорувати.
- Порції двох вікових груп (120г // 140г) не зберігати — лише назва страви.
- Алергени з дужок (МП, Г, Я, Р, А...) винести в окреме поле.
"""
import json
from google import genai
from google.genai import types

from app import config

_PROMPT = """Ти — парсер шкільного меню. На вході PDF з меню на тиждень (5 днів).

Витягни страви ТІЛЬКИ для трьох прийомів їжі: "Сніданок", "Обід", "Вечеря".
КАТЕГОРИЧНО ПРОІГНОРУЙ розділ "Полуденок" — жодної його страви у відповідь не включай.

Для кожної страви:
- "day": один із [Понеділок, Вівторок, Середа, Четвер, П’ятниця]
- "category": один із [Сніданок, Обід, Вечеря]
- "dish": НАЗВА страви БЕЗ грамів і порцій (прибери "120г // 140г", "200/250г" тощо).
  Напої (чай, какао, компот, морс) теж вважай стравами відповідної категорії.
- "allergens": рядок позначок із дужок через кому (напр. "МП,Я"). Якщо немає — "".

Поверни СТРОГО валідний JSON-масив об'єктів, без markdown, без коментарів, без ```.
Приклад одного елемента:
{"day":"Понеділок","category":"Сніданок","dish":"Омлет з овочами","allergens":"МП,Я"}
"""


class GeminiParser:
    def __init__(self):
        self._client = genai.Client(api_key=config.GEMINI_API_KEY)

    def parse_menu(self, pdf_bytes: bytes) -> list[dict]:
        """Повертає список страв (без Полуденка)."""
        response = self._client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
                _PROMPT,
            ],
        )
        text = (response.text or "").strip()
        # прибрати можливі markdown-огородження
        if text.startswith("```"):
            text = text.strip("`")
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
        text = text.strip()

        data = json.loads(text)

        # Захисна фільтрація: викидаємо все, що не з трьох дозволених категорій
        # (навіть якщо модель випадково пропустила Полуденок).
        cleaned = []
        for item in data:
            cat = (item.get("category") or "").strip()
            if cat not in config.CATEGORIES:
                continue
            day = (item.get("day") or "").strip()
            if day not in config.WEEKDAYS:
                continue
            dish = (item.get("dish") or "").strip()
            if not dish:
                continue
            cleaned.append({
                "day": day,
                "category": cat,
                "dish": dish,
                "allergens": (item.get("allergens") or "").strip(),
            })
        return cleaned
