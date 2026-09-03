"""Допоміжні функції: визначення ролі та надсилання сповіщень."""
from app import config


def resolve_role(sheets, chat_id: int) -> tuple[str, dict | None]:
    """
    Визначає роль за chat_id (ієрархія адмін→вчитель→батьки).
    Повертає (роль, запис_користувача|None).
    """
    if chat_id == config.ADMIN_CHAT_ID:
        return config.ROLE_ADMIN, None

    user = sheets.get_user_by_chat(chat_id)
    if user and user.get("роль") == config.ROLE_TEACHER:
        return config.ROLE_TEACHER, user

    students = sheets.get_students_by_parent(chat_id)
    if students:
        return config.ROLE_PARENT, {"students": students}

    return "unknown", None


async def notify_teacher_confirmation(bot, teacher_chat_id, pib, day_date, dishes: dict):
    """
    Сповіщення вчителю про підтвердження меню (TC-06).
    Викликається лише при ПЕРШОМУ підтвердженні дня.
    """
    lines = []
    for category, items in dishes.items():
        if items:
            lines.append(f"  {category}: {', '.join(items)}")
    body = "\n".join(lines) if lines else "  (нічого не обрано)"
    text = f"✅ Батьки учня {pib} обрали меню на {day_date}:\n{body}"
    try:
        await bot.send_message(teacher_chat_id, text)
    except Exception:
        pass  # вчитель міг не запустити бота — не валимо потік


async def broadcast_parents(bot, sheets, text: str):
    """Масова розсилка всім батькам (TC: команда розсилки)."""
    ws_users = sheets.get_students_by_class  # not used; iterate all
    sent = set()
    # зібрати всі батьківські chat_id з довідника
    all_records = sheets._ws(config.SHEET_USERS).get_all_records()
    count = 0
    for r in all_records:
        for slot in ("chat_id_1", "chat_id_2"):
            cid = r.get(slot)
            if cid and str(cid) not in sent and r.get("роль") == config.ROLE_PARENT:
                sent.add(str(cid))
                try:
                    await bot.send_message(int(cid), text)
                    count += 1
                except Exception:
                    pass
    return count
