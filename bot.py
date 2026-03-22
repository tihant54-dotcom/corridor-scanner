"""
Telegram Bot — Коридоры Fonbet/Maxline
Встроенный веб-сервер: отдаёт Mini App и API с реальными данными
"""
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, BotCommand, MenuButtonWebApp,
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiohttp import web

import config
from parser import CorridorScanner, Corridor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

PORT = int(os.getenv("PORT", 8080))
RAILWAY_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
if RAILWAY_URL and not RAILWAY_URL.startswith("http"):
    RAILWAY_URL = f"https://{RAILWAY_URL}"

WEBAPP_URL = os.getenv("WEBAPP_URL", f"{RAILWAY_URL}" if RAILWAY_URL else "")


# ─────────────────────────────────────────────
# STATE
# ─────────────────────────────────────────────
class State:
    def __init__(self):
        self.subscribers: set[int] = set()
        self.is_auto = False
        self.last: list[Corridor] = []
        self.scans = 0
        self.found = 0
        self.last_time = "—"
        self.min_profit = 0.5
        self.sports = {"basketball", "volleyball"}
        self._load()

    def save(self):
        with open("state.json", "w") as f:
            json.dump({
                "subscribers": list(self.subscribers),
                "min_profit": self.min_profit,
                "sports": list(self.sports),
            }, f)

    def _load(self):
        if os.path.exists("state.json"):
            try:
                d = json.load(open("state.json"))
                self.subscribers = set(d.get("subscribers", []))
                self.min_profit = d.get("min_profit", 0.5)
                self.sports = set(d.get("sports", ["basketball", "volleyball"]))
            except Exception:
                pass


st = State()
router = Router()


# ─────────────────────────────────────────────
# WEB SERVER — отдаёт HTML и API
# ─────────────────────────────────────────────

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "*",
}

# Кешируем последние результаты скана
_scan_cache = {"time": None, "corridors": [], "error": None}


async def handle_index(request):
    html_path = Path(__file__).parent / "index.html"
    if html_path.exists():
        return web.FileResponse(html_path)
    return web.Response(text="index.html not found", status=404)


async def handle_scan(request):
    """Реальный скан — Railway сервер делает запросы к Fonbet/Maxline"""
    try:
        scanner = CorridorScanner(demo_mode=False)
        corridors = await scanner.scan_all()
        _scan_cache["corridors"] = [c.to_dict() for c in corridors]
        _scan_cache["time"] = datetime.now().strftime("%H:%M:%S")
        _scan_cache["error"] = None
        logger.info(f"API scan: {len(corridors)} коридоров")
        return web.json_response({
            "ok": True,
            "corridors": _scan_cache["corridors"],
            "count": len(corridors),
            "time": _scan_cache["time"],
        }, headers=CORS_HEADERS)
    except Exception as e:
        logger.error(f"API scan error: {e}")
        return web.json_response(
            {"ok": False, "error": str(e), "corridors": []},
            headers=CORS_HEADERS, status=500
        )


async def handle_health(request):
    return web.json_response({"ok": True, "status": "running"}, headers=CORS_HEADERS)


async def handle_options(request):
    return web.Response(headers=CORS_HEADERS)


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/index.html", handle_index)
    app.router.add_get("/api/scan", handle_scan)
    app.router.add_get("/health", handle_health)
    app.router.add_route("OPTIONS", "/{path_info:.*}", handle_options)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info(f"Веб-сервер запущен на порту {PORT}")
    if RAILWAY_URL:
        logger.info(f"URL: {RAILWAY_URL}")


# ─────────────────────────────────────────────
# KEYBOARDS
# ─────────────────────────────────────────────
def main_kb() -> InlineKeyboardMarkup:
    rows = []
    if WEBAPP_URL:
        rows.append([InlineKeyboardButton(
            text="🌐 Открыть дашборд",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )])
    rows.append([
        InlineKeyboardButton(text="🔍 Скан", callback_data="scan"),
        InlineKeyboardButton(text="📊 Стат", callback_data="stats"),
    ])
    rows.append([
        InlineKeyboardButton(
            text=f"🔔 Авто: {'ВКЛ ✅' if st.is_auto else 'ВЫКЛ ❌'}",
            callback_data="toggle_auto"
        ),
        InlineKeyboardButton(text="⚙️ Фильтры", callback_data="filters"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back")]
    ])


def filters_kb() -> InlineKeyboardMarkup:
    bb = "✅" if "basketball" in st.sports else "☑️"
    vb = "✅" if "volleyball" in st.sports else "☑️"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🏀 Баскетбол {bb}", callback_data="f_bb"),
            InlineKeyboardButton(text=f"🏐 Волейбол {vb}", callback_data="f_vb"),
        ],
        [InlineKeyboardButton(text=f"💰 Мин. профит: {st.min_profit}%", callback_data="noop")],
        [
            InlineKeyboardButton(text="➖ 0.5%", callback_data="p_minus"),
            InlineKeyboardButton(text="➕ 0.5%", callback_data="p_plus"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")],
    ])


# ─────────────────────────────────────────────
# HANDLERS
# ─────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message):
    st.subscribers.add(msg.from_user.id)
    st.save()
    text = (
        "👋 <b>Corridor Scanner</b>\n"
        "Fonbet × Maxline — 🏀 🏐\n"
        "─────────────────────\n"
        "Ищет арбитражные коридоры по тоталам.\n\n"
        f"💰 Мин. профит: <b>{st.min_profit}%</b>"
    )
    if not WEBAPP_URL:
        text += "\n\n⚠️ Добавь WEBAPP_URL в Railway Variables"
    await msg.answer(text, reply_markup=main_kb(), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "back")
async def cb_back(cq: CallbackQuery):
    await cq.message.edit_text("📱 <b>Главное меню</b>", reply_markup=main_kb(), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "scan")
async def cb_scan(cq: CallbackQuery):
    await cq.answer("🔍 Сканирую...")
    await run_scan_and_reply(cq.message)


@router.callback_query(F.data == "toggle_auto")
async def cb_toggle_auto(cq: CallbackQuery):
    st.is_auto = not st.is_auto
    if st.is_auto:
        await cq.answer("🔔 Авто-скан запущен!")
        asyncio.create_task(auto_loop(cq.bot))
    else:
        await cq.answer("🔕 Авто-скан остановлен")
    await cq.message.edit_reply_markup(reply_markup=main_kb())


@router.callback_query(F.data == "filters")
async def cb_filters(cq: CallbackQuery):
    await cq.answer()
    await cq.message.edit_text("⚙️ <b>Фильтры</b>", reply_markup=filters_kb(), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "f_bb")
async def cb_fbb(cq: CallbackQuery):
    "basketball" in st.sports and st.sports.discard("basketball") or st.sports.add("basketball")
    st.save()
    await cq.answer()
    await cq.message.edit_reply_markup(reply_markup=filters_kb())


@router.callback_query(F.data == "f_vb")
async def cb_fvb(cq: CallbackQuery):
    "volleyball" in st.sports and st.sports.discard("volleyball") or st.sports.add("volleyball")
    st.save()
    await cq.answer()
    await cq.message.edit_reply_markup(reply_markup=filters_kb())


@router.callback_query(F.data == "p_minus")
async def cb_pminus(cq: CallbackQuery):
    st.min_profit = max(0.1, round(st.min_profit - 0.5, 1))
    st.save()
    await cq.answer(f"{st.min_profit}%")
    await cq.message.edit_reply_markup(reply_markup=filters_kb())


@router.callback_query(F.data == "p_plus")
async def cb_pplus(cq: CallbackQuery):
    st.min_profit = round(st.min_profit + 0.5, 1)
    st.save()
    await cq.answer(f"{st.min_profit}%")
    await cq.message.edit_reply_markup(reply_markup=filters_kb())


@router.callback_query(F.data == "stats")
async def cb_stats(cq: CallbackQuery):
    await cq.answer()
    bb = sum(1 for c in st.last if c.sport == "basketball")
    vb = sum(1 for c in st.last if c.sport == "volleyball")
    await cq.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"🔄 Сканирований: <b>{st.scans}</b>\n"
        f"⏱ Последнее: <b>{st.last_time}</b>\n"
        f"💰 Найдено всего: <b>{st.found}</b>\n\n"
        f"🏀 Баскетбол: <b>{bb}</b>\n"
        f"🏐 Волейбол: <b>{vb}</b>\n\n"
        f"💰 Мин. профит: {st.min_profit}%",
        reply_markup=back_kb(), parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data == "noop")
async def cb_noop(cq: CallbackQuery):
    await cq.answer()


# ─────────────────────────────────────────────
# SCAN LOGIC
# ─────────────────────────────────────────────
async def do_scan() -> list[Corridor]:
    scanner = CorridorScanner(demo_mode=False)
    corridors = await scanner.scan_all()
    return [c for c in corridors
            if c.sport in st.sports and c.profit_percent >= st.min_profit]


async def run_scan_and_reply(target: Message):
    msg = await target.answer("⏳ Сканирую реальные данные...")
    corridors = await do_scan()
    await msg.delete()

    st.scans += 1
    st.found += len(corridors)
    st.last = corridors
    st.last_time = datetime.now().strftime("%d.%m %H:%M:%S")

    if not corridors:
        await target.answer(
            "🔍 Коридоров не найдено.\n"
            f"⏱ {st.last_time}\n"
            "💡 Снизьте мин. профит в фильтрах.",
            reply_markup=back_kb()
        )
        return

    await target.answer(
        f"✅ <b>Найдено {len(corridors)} коридоров</b> — {st.last_time}",
        parse_mode=ParseMode.HTML
    )
    for c in corridors[:8]:
        await target.answer(c.to_message(), parse_mode=ParseMode.HTML)
        await asyncio.sleep(0.3)


async def auto_loop(bot: Bot):
    logger.info("Авто-скан запущен")
    while st.is_auto:
        try:
            corridors = await do_scan()
            st.scans += 1
            st.found += len(corridors)
            st.last = corridors
            st.last_time = datetime.now().strftime("%d.%m %H:%M:%S")
            if corridors:
                hdr = f"🔔 <b>Коридоры!</b> [{st.last_time}]\nНайдено: <b>{len(corridors)}</b>"
                for uid in st.subscribers:
                    try:
                        await bot.send_message(uid, hdr, parse_mode=ParseMode.HTML)
                        for c in corridors[:5]:
                            await bot.send_message(uid, c.to_message(), parse_mode=ParseMode.HTML)
                            await asyncio.sleep(0.2)
                    except Exception as e:
                        logger.warning(f"Send {uid}: {e}")
        except Exception as e:
            logger.error(f"Auto scan: {e}")
        await asyncio.sleep(config.PARSE_INTERVAL)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
async def main():
    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    if WEBAPP_URL:
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="📊 Дашборд",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            )
        except Exception as e:
            logger.warning(f"Меню-кнопка: {e}")

    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="scan", description="Сканировать"),
    ])

    await start_web_server()
    logger.info(f"Бот запущен | Подписчиков={len(st.subscribers)}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
