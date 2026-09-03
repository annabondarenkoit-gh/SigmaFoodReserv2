"""
Конфігурація застосунку SigmaFood.
Усі секрети читаються зі змінних оточення (Railway → Variables).
У код секрети НЕ потрапляють.
"""
import os
from zoneinfo import ZoneInfo

# --- Секрети (Railway Variables) ---
BOT_TOKEN = os.environ["BOT_TOKEN"]                      # від @BotFather
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]            # ключ Google Gemini
GOOGLE_CREDENTIALS = os.environ["GOOGLE_CREDENTIALS"]    # JSON сервісного акаунта (як рядок)

# ID папки/таблиці Google Sheets у папці SigmaFoodRezerv.
# Використовуємо ОДНУ Google-таблицю з кількома аркушами (простіше й надійніше,
# ніж кілька окремих файлів; менше викликів API).
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]

# Публічний HTTPS-URL сервісу на Railway (напр. https://sigmafood.up.railway.app)
# Потрібен для Telegram Web App і webhook.
BASE_URL = os.environ["BASE_URL"].rstrip("/")

# Chat ID головного адміністратора (початковий суперкористувач).
# Вписується вручну один раз; далі адмін додає вчителів через бота.
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])

# --- Константи ---
TZ = ZoneInfo("Europe/Kyiv")   # часовий пояс для дедлайну 00:00

# Порядок днів тижня (робочий тиждень Пн–Пт)
WEEKDAYS = ["Понеділок", "Вівторок", "Середа", "Четвер", "П’ятниця"]

# Категорії страв, які бачать батьки (розділ «Полуденок» ІГНОРУЄТЬСЯ повністю)
CATEGORIES = ["Сніданок", "Обід", "Вечеря"]

# Розшифровка позначок алергенів (для показу у Web App)
ALLERGENS = {
    "МП": "молочні продукти",
    "Г": "глютен",
    "Я": "яйця",
    "Р": "риба",
    "А": "арахіс",
}

# Назви аркушів у Google-таблиці
SHEET_MENU = "База_Меню"
SHEET_USERS = "Довідник_Користувачів"
SHEET_ORDERS = "База_замовлень"
SHEET_KITCHEN = "Для кухні"

# Ролі
ROLE_ADMIN = "admin"
ROLE_TEACHER = "teacher"
ROLE_PARENT = "parent"
