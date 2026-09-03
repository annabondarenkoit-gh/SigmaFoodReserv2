"""
Сервіс роботи з Google Sheets.
Одна таблиця (SPREADSHEET_ID) з 4 аркушами. Автостворення схеми при старті.

Схема аркушів:

  База_Меню:            week | day | category | dish | allergens
  Довідник_Користувачів: user_id | ПІБ | роль | клас | chat_id_1 | chat_id_2 | teacher_chat_id
  База_замовлень:        order_id | user_id | week | day | dishes_json | is_staff_modified | is_locked | timestamp
  Для кухні:             week | day | category | dish | кількість

Примітки:
- Порції двох вікових груп НЕ зберігаємо — лише назва страви.
- Розділ «Полуденок» у меню не потрапляє (фільтрується на етапі парсингу).
- "Для кухні" перераховується з База_замовлень (не редагується вручну).
"""
import json
import gspread
from google.oauth2.service_account import Credentials

from app import config

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Заголовки кожного аркуша
_HEADERS = {
    config.SHEET_MENU: ["week", "day", "category", "dish", "allergens"],
    config.SHEET_USERS: [
        "user_id", "ПІБ", "роль", "клас",
        "chat_id_1", "chat_id_2", "teacher_chat_id",
    ],
    config.SHEET_ORDERS: [
        "order_id", "user_id", "week", "day",
        "dishes_json", "is_staff_modified", "is_locked", "timestamp",
    ],
    config.SHEET_KITCHEN: ["week", "day", "category", "dish", "кількість"],
}


class SheetsService:
    def __init__(self):
        creds_info = json.loads(config.GOOGLE_CREDENTIALS)
        creds = Credentials.from_service_account_info(creds_info, scopes=_SCOPES)
        self._gc = gspread.authorize(creds)
        self._ss = self._gc.open_by_key(config.SPREADSHEET_ID)
        self._ensure_sheets()

    # --- Ініціалізація схеми ---
    def _ensure_sheets(self):
        """Створює відсутні аркуші й заголовки. Безпечно викликати багато разів."""
        existing = {ws.title: ws for ws in self._ss.worksheets()}
        for title, headers in _HEADERS.items():
            if title not in existing:
                ws = self._ss.add_worksheet(title=title, rows=1000, cols=len(headers))
                ws.append_row(headers)
            else:
                ws = existing[title]
                first_row = ws.row_values(1)
                if first_row != headers:
                    ws.update("A1", [headers])
        # Прибрати дефолтний "Sheet1", якщо він порожній і зайвий
        if "Sheet1" in existing and "Sheet1" not in _HEADERS:
            try:
                self._ss.del_worksheet(existing["Sheet1"])
            except Exception:
                pass

    def _ws(self, title):
        return self._ss.worksheet(title)

    # ================= МЕНЮ =================
    def replace_menu(self, week: int, rows: list[dict]):
        """
        Повністю замінює меню на тиждень `week`.
        rows: [{"day","category","dish","allergens"}...]
        """
        ws = self._ws(config.SHEET_MENU)
        all_values = ws.get_all_records()
        # лишаємо записи інших тижнів
        keep = [r for r in all_values if str(r.get("week")) != str(week)]

        ws.clear()
        ws.append_row(_HEADERS[config.SHEET_MENU])
        payload = []
        for r in keep:
            payload.append([r["week"], r["day"], r["category"], r["dish"], r["allergens"]])
        for r in rows:
            payload.append([week, r["day"], r["category"], r["dish"], r.get("allergens", "")])
        if payload:
            ws.append_rows(payload)

    def get_menu(self, week: int, day: str) -> list[dict]:
        """Страви конкретного дня, згруповані за категоріями (для Web App)."""
        ws = self._ws(config.SHEET_MENU)
        records = ws.get_all_records()
        return [
            {"category": r["category"], "dish": r["dish"], "allergens": r["allergens"]}
            for r in records
            if str(r["week"]) == str(week) and r["day"] == day
        ]

    # ================= КОРИСТУВАЧІ =================
    def get_user_by_chat(self, chat_id: int) -> dict | None:
        """Знаходить користувача (вчитель/адмін) за його особистим chat_id."""
        ws = self._ws(config.SHEET_USERS)
        for r in ws.get_all_records():
            if str(r.get("chat_id_1")) == str(chat_id) or str(r.get("teacher_chat_id")) == str(chat_id):
                return r
        return None

    def get_students_by_parent(self, chat_id: int) -> list[dict]:
        """Учні, до яких прив'язаний цей батьківський chat_id (у будь-який зі слотів)."""
        ws = self._ws(config.SHEET_USERS)
        out = []
        for r in ws.get_all_records():
            if r.get("роль") != config.ROLE_PARENT:
                # учні зберігаються як роль parent-прив'язка? — ні: учень = окремий запис
                pass
            if str(r.get("chat_id_1")) == str(chat_id) or str(r.get("chat_id_2")) == str(chat_id):
                out.append(r)
        return out

    def get_students_by_class(self, klass: str) -> list[dict]:
        ws = self._ws(config.SHEET_USERS)
        return [r for r in ws.get_all_records() if str(r.get("клас")) == str(klass)]

    def add_student(self, pib: str, klass: str, parent1: str, parent2: str, teacher_chat: int) -> str:
        """Додає учня. Повертає user_id."""
        ws = self._ws(config.SHEET_USERS)
        records = ws.get_all_records()
        new_id = f"stu_{len(records) + 1:04d}"
        ws.append_row([
            new_id, pib, config.ROLE_PARENT, klass,
            parent1 or "", parent2 or "", teacher_chat,
        ])
        return new_id

    def add_teacher(self, pib: str, klass: str, chat_id: int) -> str:
        ws = self._ws(config.SHEET_USERS)
        records = ws.get_all_records()
        new_id = f"tch_{len(records) + 1:04d}"
        ws.append_row([new_id, pib, config.ROLE_TEACHER, klass, chat_id, "", ""])
        return new_id

    # ================= ЗАМОВЛЕННЯ =================
    def get_order(self, user_id: str, week: int, day: str) -> dict | None:
        ws = self._ws(config.SHEET_ORDERS)
        for r in ws.get_all_records():
            if (r["user_id"] == user_id and str(r["week"]) == str(week)
                    and r["day"] == day):
                return r
        return None

    def upsert_order(self, user_id: str, week: int, day: str,
                     dishes: dict, staff_modified: bool, locked: bool, timestamp: str):
        """
        Створює або оновлює замовлення (учень × день).
        dishes: {"Сніданок":[...], "Обід":[...], "Вечеря":[...]}
        """
        ws = self._ws(config.SHEET_ORDERS)
        records = ws.get_all_records()
        dishes_json = json.dumps(dishes, ensure_ascii=False)

        for idx, r in enumerate(records, start=2):  # рядок 1 = заголовки
            if (r["user_id"] == user_id and str(r["week"]) == str(week)
                    and r["day"] == day):
                ws.update(f"E{idx}:H{idx}", [[
                    dishes_json, str(staff_modified), str(locked), timestamp
                ]])
                return r["order_id"]

        new_id = f"ord_{len(records) + 1:05d}"
        ws.append_row([
            new_id, user_id, week, day, dishes_json,
            str(staff_modified), str(locked), timestamp,
        ])
        return new_id

    def get_orders_for_week(self, week: int) -> list[dict]:
        ws = self._ws(config.SHEET_ORDERS)
        return [r for r in ws.get_all_records() if str(r["week"]) == str(week)]

    # ================= ДЛЯ КУХНІ =================
    def rebuild_kitchen(self, week: int):
        """
        Перераховує аркуш «Для кухні» з База_замовлень:
        для кожної (day, category, dish) — скільки порцій замовлено.
        """
        orders = self.get_orders_for_week(week)
        counter: dict[tuple, int] = {}
        for o in orders:
            try:
                dishes = json.loads(o["dishes_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            for category, items in dishes.items():
                for dish in items:
                    key = (o["day"], category, dish)
                    counter[key] = counter.get(key, 0) + 1

        ws = self._ws(config.SHEET_KITCHEN)
        # чистимо лише рядки цього тижня
        keep = [r for r in ws.get_all_records() if str(r["week"]) != str(week)]
        ws.clear()
        ws.append_row(_HEADERS[config.SHEET_KITCHEN])
        payload = [[r["week"], r["day"], r["category"], r["dish"], r["кількість"]] for r in keep]
        for (day, category, dish), qty in sorted(counter.items()):
            payload.append([week, day, category, dish, qty])
        if payload:
            ws.append_rows(payload)
        return counter
