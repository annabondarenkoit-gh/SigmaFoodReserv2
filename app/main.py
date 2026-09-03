"""
Головний застосунок SigmaFood.
Єдиний сервіс на Railway: FastAPI обслуговує і webhook бота, і Web App API.

Ендпоінти:
  POST /webhook/{token}       — приймає апдейти Telegram
  GET  /webapp                — сторінка вибору страв (Web App)
  GET  /api/menu              — меню на тиждень (для Web App)
  POST /api/order             — збереження вибору батьків (TC-03)
  GET  /health                — healthcheck для Railway
"""
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher
from aiogram.types import Update

from app import config
from app.services.sheets import SheetsService
from app.services import deadline, notify
from app.handlers import router

# --- Глобальні об'єкти ---
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()
dp.include_router(router)

sheets = SheetsService()
# прокидаємо спільні залежності у workflow_data (доступні в хендлерах)
dp["sheets"] = sheets
dp["bot"] = bot


@asynccontextmanager
async def lifespan(app: FastAPI):
    webhook_url = f"{config.BASE_URL}/webhook/{config.BOT_TOKEN}"
    await bot.set_webhook(webhook_url, drop_pending_updates=True)
    yield
    await bot.delete_webhook()
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook/{token}")
async def telegram_webhook(token: str, request: Request):
    if token != config.BOT_TOKEN:
        raise HTTPException(status_code=403, detail="forbidden")
    data = await request.json()
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}


# ============ Web App API ============
@app.get("/api/menu")
async def api_menu(week: int, user_id: str):
    """Повертає меню на тиждень із поточним вибором учня та статусами блокування."""
    result = {"week": week, "days": []}
    order_cache = {}
    for day in config.WEEKDAYS:
        menu = sheets.get_menu(week, day)
        # згрупувати за категоріями у порядку CATEGORIES
        by_cat = {c: [] for c in config.CATEGORIES}
        for m in menu:
            if m["category"] in by_cat:
                by_cat[m["category"]].append({
                    "dish": m["dish"],
                    "allergens": _decode_allergens(m["allergens"]),
                })

        order = sheets.get_order(user_id, week, day)
        chosen = {}
        staff_modified = False
        if order:
            try:
                chosen = json.loads(order["dishes_json"])
            except (json.JSONDecodeError, TypeError):
                chosen = {}
            staff_modified = str(order.get("is_staff_modified")).lower() == "true"

        locked = deadline.is_locked_for_parents(week, day)
        result["days"].append({
            "day": day,
            "date": str(deadline.date_of_weekday(week, day)),
            "categories": by_cat,
            "chosen": chosen,
            "locked": locked,
            "staff_modified": staff_modified,
        })
    return JSONResponse(result)


@app.post("/api/order")
async def api_order(request: Request):
    """
    Збереження вибору батьків (TC-03).
    Тіло: {user_id, week, day, dishes:{Сніданок:[...],Обід:[...],Вечеря:[...]}}
    """
    data = await request.json()
    user_id = data["user_id"]
    week = int(data["week"])
    day = data["day"]
    dishes = data.get("dishes", {})

    # Правило блокування (TC-04): якщо день заблоковано — відмова
    if deadline.is_locked_for_parents(week, day):
        return JSONResponse({"ok": False, "error": "locked"}, status_code=423)

    existing = sheets.get_order(user_id, week, day)
    first_confirmation = existing is None

    ts = deadline.now_kyiv().isoformat()
    sheets.upsert_order(
        user_id=user_id, week=week, day=day, dishes=dishes,
        staff_modified=False, locked=False, timestamp=ts,
    )
    sheets.rebuild_kitchen(week)

    # Сповіщення вчителю лише при першому підтвердженні (TC-06)
    if first_confirmation:
        student = _find_student(user_id)
        if student and student.get("teacher_chat_id"):
            await notify.notify_teacher_confirmation(
                bot, int(student["teacher_chat_id"]),
                student["ПІБ"], str(deadline.date_of_weekday(week, day)), dishes,
            )
    return JSONResponse({"ok": True})


def _find_student(user_id: str) -> dict | None:
    for r in sheets._ws(config.SHEET_USERS).get_all_records():
        if r.get("user_id") == user_id:
            return r
    return None


def _decode_allergens(raw: str) -> list[str]:
    if not raw:
        return []
    out = []
    for code in [c.strip() for c in raw.split(",") if c.strip()]:
        out.append(config.ALLERGENS.get(code, code))
    return out


# ============ Статика Web App ============
app.mount("/static", StaticFiles(directory="webapp"), name="static")


@app.get("/webapp")
async def webapp_page():
    return FileResponse("webapp/index.html")
