"""
Обробники команд Telegram-бота.
Роутинг за ролями (ієрархія адмін→вчитель→батьки).

Команди:
  /start                     — вітання + меню за роллю
  PDF-документ (адмін)       — завантаження та парсинг меню (TC-01)
  /broadcast <текст>         — розсилка батькам (адмін)
  /report                    — .xlsx-звіт для кухні (адмін, TC-07)
  /add_teacher ПІБ|клас|chat_id       — додати вчителя (адмін)
  /add_student ПІБ|клас|chat1|chat2   — додати учня (вчитель, TC-02)
  /class                     — статуси замовлень класу (вчитель)
  Web App кнопка (батьки)    — відкрити вибір страв
"""
from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton,
    BufferedInputFile,
)

from app import config
from app.services import deadline, notify, report

router = Router()


def _role(sheets, chat_id):
    return notify.resolve_role(sheets, chat_id)


# ==================== /start ====================
@router.message(CommandStart())
async def cmd_start(message: Message, sheets):
    role, data = _role(sheets, message.chat.id)

    if role == config.ROLE_ADMIN:
        await message.answer(
            "👋 Вітаю, адміністраторе!\n\n"
            "Доступні дії:\n"
            "• Надішліть PDF-файл меню — я його розпарсю\n"
            "• /broadcast <текст> — розсилка батькам\n"
            "• /report — звіт для кухні (.xlsx)\n"
            "• /add_teacher ПІБ | клас | chat_id — додати вчителя"
        )
    elif role == config.ROLE_TEACHER:
        await message.answer(
            f"👩‍🏫 Вітаю, {data['ПІБ']}! Ваш клас: {data['клас']}.\n\n"
            "• /add_student ПІБ | клас | chat_id_1 | chat_id_2 — додати учня\n"
            "• /class — статуси замовлень вашого класу\n\n"
            "Ви отримуватимете сповіщення, коли батьки підтверджують меню."
        )
    elif role == config.ROLE_PARENT:
        week = deadline.current_week_number()
        await _send_webapp_button(message, data["students"], week)
    else:
        await message.answer(
            "Вітаю! Ваш акаунт ще не зареєстрований у системі.\n"
            "Зверніться до класного керівника, щоб вас додали."
        )


async def _send_webapp_button(message, students, week):
    student = students[0]
    user_id = student["user_id"]
    url = f"{config.BASE_URL}/webapp?user_id={user_id}&week={week}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"🍽 Обрати харчування — {student['ПІБ']}",
            web_app=WebAppInfo(url=url),
        )
    ]])
    await message.answer(
        "Оберіть харчування дитини на тиждень 👇",
        reply_markup=kb,
    )


# ==================== АДМІН: PDF-меню (TC-01) ====================
@router.message(F.document)
async def handle_pdf(message: Message, sheets, bot):
    role, _ = _role(sheets, message.chat.id)
    if role != config.ROLE_ADMIN:
        return
    doc = message.document
    if not (doc.mime_type == "application/pdf" or doc.file_name.lower().endswith(".pdf")):
        await message.answer("Надішліть, будь ласка, PDF-файл меню.")
        return

    await message.answer("⏳ Обробляю меню через Gemini…")
    file = await bot.get_file(doc.file_id)
    buf = await bot.download_file(file.file_path)
    pdf_bytes = buf.read()

    from app.services.gemini_parser import GeminiParser
    parser = GeminiParser()
    try:
        rows = parser.parse_menu(pdf_bytes)
    except Exception as e:
        await message.answer(f"❌ Не вдалося розпарсити меню: {e}")
        return

    week = deadline.current_week_number()
    sheets.replace_menu(week, rows)

    from collections import Counter
    cats = Counter(r["category"] for r in rows)
    summary = ", ".join(f"{c}: {n}" for c, n in cats.items())
    await message.answer(
        f"✅ Меню на тиждень №{week} збережено.\n"
        f"Витягнуто страв: {len(rows)} ({summary}).\n"
        f"Розділ «Полуденок» проігноровано.\n\n"
        f"Тепер можна зробити розсилку: /broadcast Просимо обрати харчування на тиждень"
    )


# ==================== АДМІН: розсилка ====================
@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, sheets, bot):
    role, _ = _role(sheets, message.chat.id)
    if role != config.ROLE_ADMIN:
        return
    text = message.text.partition(" ")[2].strip()
    if not text:
        text = "Просимо обрати харчування на тиждень 🍽"
    count = await notify.broadcast_parents(bot, sheets, text)
    await message.answer(f"📨 Розіслано {count} батькам.")


# ==================== АДМІН: звіт (TC-07) ====================
@router.message(Command("report"))
async def cmd_report(message: Message, sheets):
    role, _ = _role(sheets, message.chat.id)
    if role != config.ROLE_ADMIN:
        return
    week = deadline.current_week_number()
    await message.answer("⏳ Формую звіт…")
    xlsx = report.build_report(sheets, week)
    await message.answer_document(
        BufferedInputFile(xlsx, filename=f"Звіт_кухня_тиждень_{week}.xlsx"),
        caption=f"📊 Звіт для кухні, тиждень №{week}",
    )


# ==================== АДМІН: додати вчителя ====================
@router.message(Command("add_teacher"))
async def cmd_add_teacher(message: Message, sheets):
    role, _ = _role(sheets, message.chat.id)
    if role != config.ROLE_ADMIN:
        return
    payload = message.text.partition(" ")[2]
    parts = [p.strip() for p in payload.split("|")]
    if len(parts) != 3:
        await message.answer("Формат: /add_teacher ПІБ | клас | chat_id")
        return
    pib, klass, chat_id = parts
    sheets.add_teacher(pib, klass, int(chat_id))
    await message.answer(f"✅ Вчителя {pib} (клас {klass}) додано.")


# ==================== ВЧИТЕЛЬ: додати учня (TC-02) ====================
@router.message(Command("add_student"))
async def cmd_add_student(message: Message, sheets):
    role, data = _role(sheets, message.chat.id)
    if role != config.ROLE_TEACHER:
        await message.answer("Ця команда доступна лише вчителям.")
        return
    payload = message.text.partition(" ")[2]
    parts = [p.strip() for p in payload.split("|")]
    if len(parts) < 3:
        await message.answer(
            "Формат: /add_student ПІБ | клас | chat_id_1 | chat_id_2(необов.)"
        )
        return
    pib = parts[0]
    klass = parts[1]
    if str(klass) != str(data["клас"]):
        await message.answer(
            f"❌ Ви можете додавати учнів лише свого класу ({data['клас']})."
        )
        return
    parent1 = parts[2] if len(parts) > 2 else ""
    parent2 = parts[3] if len(parts) > 3 else ""
    sid = sheets.add_student(pib, klass, parent1, parent2, message.chat.id)
    await message.answer(f"✅ Учня {pib} додано (ID {sid}).")


# ==================== ВЧИТЕЛЬ: статуси класу ====================
@router.message(Command("class"))
async def cmd_class(message: Message, sheets):
    role, data = _role(sheets, message.chat.id)
    if role != config.ROLE_TEACHER:
        return
    week = deadline.current_week_number()
    students = sheets.get_students_by_class(data["клас"])
    students = [s for s in students if s.get("роль") == config.ROLE_PARENT]
    if not students:
        await message.answer("У вашому класі ще немає учнів.")
        return

    lines = [f"📋 Клас {data['клас']}, тиждень №{week}:"]
    for s in students:
        filled = 0
        for day in config.WEEKDAYS:
            if sheets.get_order(s["user_id"], week, day):
                filled += 1
        lines.append(f"• {s['ПІБ']}: {filled}/{len(config.WEEKDAYS)} днів")
    await message.answer("\n".join(lines))
