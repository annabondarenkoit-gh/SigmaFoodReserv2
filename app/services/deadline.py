"""
Логіка блокування редагування о 00:00 дня харчування (Київ).

Правило (TC-04):
- Вибір на конкретний день блокується для батьків опівночі того ж дня.
  Тобто після 00:00 понеділка вибір на понеділок редагувати не можна.
- Персонал (вчитель/адмін) може коригувати й після блокування (TC-05).
"""
from datetime import datetime, date, timedelta

from app import config


def now_kyiv() -> datetime:
    return datetime.now(config.TZ)


def current_week_number(ref: date | None = None) -> int:
    """ISO-номер тижня — використовується як ідентифікатор тижня меню."""
    ref = ref or now_kyiv().date()
    return ref.isocalendar().week


def date_of_weekday(week: int, day_name: str, ref: date | None = None) -> date | None:
    """
    Обчислює календарну дату для (номер ISO-тижня, назва дня).
    Береться рік поточної дати.
    """
    if day_name not in config.WEEKDAYS:
        return None
    ref = ref or now_kyiv().date()
    weekday_index = config.WEEKDAYS.index(day_name)  # 0 = Понеділок
    # перший день ISO-тижня
    monday = date.fromisocalendar(ref.year, week, 1)
    return monday + timedelta(days=weekday_index)


def is_locked_for_parents(week: int, day_name: str) -> bool:
    """
    True, якщо для батьків цей день уже заблокований
    (настав 00:00 дня харчування або день у минулому).
    """
    target = date_of_weekday(week, day_name)
    if target is None:
        return True
    today = now_kyiv().date()
    # заблоковано, якщо цільова дата — сьогодні або раніше
    return target <= today
