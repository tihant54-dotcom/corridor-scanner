"""
Telegram Bot — Коридоры Fonbet/Maxline
С поддержкой Mini App (Web App кнопка)
"""
import asyncio
import json
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, BotCommand,
    MenuButtonWebApp,
)
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

import config
from parser import CorridorScanner, Corridor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ]
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# WEBAPP URL —  https://tihant54-dotcom.github.io/corridor-scanner/ miniapp.html
# Варианты хостинга:
#   1. GitHub Pages (бесплатно)
#   2. Vercel / Netlify (бесплатно, drag-n-drop)
#   3. Любой VPS / хостинг
# ВАЖНО: должен быть HTTPS
# ─────────────────────────────────────────────
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://YOUR_DOMAIN/miniapp.html")

# Если ещё нет хостинга — используем демо-режим (серверный парсер)
USE_SERVER_SCAN = not WEBAPP_URL.startswith("https://YOUR")


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
        self.demo = True
        self.min_profit = 0.5
        self.sports = {"basketball", "volleyball"}
        self._load()

    def save(self):
        with open("state.json", "w") as f:
            json.dump({
                "subscribers": list(self.subscribers),
                "demo": self.demo,
                "min_profit": self.min_profit,
                "sports": list(self.sports),
            }, f)

    def _load(self):
        if os.path.exists("state.json"):
            try:
                d = json.load(open("state.json"))
                self.subscribers = set(d.get("subscribers", []))
                self.demo = d.get("demo", True)
                self.min_profit = d.get("min_profit", 0.5)
                self.sports = set(d.get("sports", ["basketball", "volleyball"]))
            except Exception:
                pass


st = State()
router = Router()


# ─────────────────────────────────────────────
# KEYBOARDS
# ─────────────────────────────────────────────
def main_kb() -> InlineKeyboardMarkup:
    rows = []

    # Кнопка Mini App (если URL настроен)
    if not WEBAPP_URL.startswith("https://YOUR"):
        rows.append([
            InlineKeyboardButton(
                text="🌐 Открыть дашборд",
                web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ])

    rows.append([
        InlineKeyboardButton(text="🔍 Скан сейчас", callback_data="scan"),
        InlineKeyboardButton(text="📊 Стат", callback_data="stats"),
    ])
    rows.append([
        InlineKeyboardButton(
            text=f"🔔 Авто: {'ВКЛ ✅' if st.is_auto else 'ВЫКЛ ❌'}",
            callback_data="toggle_auto"
        ),
        InlineKeyboardButton(
            text=f"🔧 {'Demo' if st.demo else 'Live'}",
            callback_data="toggle_demo"
        ),
    ])
    rows.append([
        InlineKeyboardButton(text="⚙️ Фильтры", callback_data="filters"),
        InlineKeyboardButton(text="ℹ️ Инфо", callback_data="help"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def filters_kb() -> InlineKeyboardMarkup:
    bb = "✅" if "basketball" in st.sports else "☑️"
    vb = "✅" if "volleyball" in st.sports else "☑️"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"🏀 Баскетбол {bb}", callback_data="f_bb"),
            InlineKeyboardButton(text=f"🏐 Волейбол {vb}", callback_data="f_vb"),
        ],
        [
            InlineKeyboardButton(text=f"💰 Мин. профит: {st.min_profit}%", callback_data="noop"),
        ],
        [
            InlineKeyboardButton(text="➖ 0.5%", callback_data="p_minus"),
            InlineKeyboardButton(text="➕ 0.5%", callback_data="p_plus"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")],
    ])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Главное меню", callback_data="back")]
    ])


# ─────────────────────────────────────────────
# HANDLERS
# ─────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message):
    st.subscribers.add(msg.from_user.id)
    st.save()

    webapp_note = (
        f"\n\n🌐 <b>Веб-дашборд доступен</b> — нажмите кнопку выше.\n"
        f"Запросы к БК идут с <b>вашего IP</b> через браузер Telegram — никаких прокси!"
        if not WEBAPP_URL.startswith("https://YOUR")
        else "\n\n⚠️ Установите WEBAPP_URL в config для активации веб-дашборда."
    )

    await msg.answer(
        f"👋 <b>Corridor Scanner</b>\n"
        f"Fonbet × Maxline — 🏀 🏐\n"
        f"─────────────────────\n"
        f"Ищет арбитражные коридоры по тоталам.\n"
        f"Запросы к API идут <b>напрямую с IP пользователя</b> через Telegram Mini App — без серверных прокси."
        f"{webapp_note}\n\n"
        f"⚙️ Режим: <b>{'Demo' if st.demo else 'Live'}</b>\n"
        f"💰 Мин. профит: <b>{st.min_profit}%</b>",
        reply_markup=main_kb(),
        parse_mode=ParseMode.HTML
    )


@router.message(Command("scan"))
async def cmd_scan(msg: Message):
    await run_scan_and_reply(msg)


@router.message(Command("webapp"))
async def cmd_webapp(msg: Message):
    if WEBAPP_URL.startswith("https://YOUR"):
        await msg.answer(
            "⚠️ <b>WEBAPP_URL не настроен</b>\n\n"
            "1. Загрузите <code>miniapp.html</code> на хостинг с HTTPS\n"
            "2. Укажите URL в переменной окружения:\n"
            "<code>WEBAPP_URL=https://yourdomain.com/miniapp.html</code>\n\n"
            "Бесплатные варианты: GitHub Pages, Netlify, Vercel",
            parse_mode=ParseMode.HTML
        )
        return

    await msg.answer(
        "🌐 Открыть веб-дашборд:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Открыть дашборд", web_app=WebAppInfo(url=WEBAPP_URL))]
        ])
    )


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


@router.callback_query(F.data == "toggle_demo")
async def cb_toggle_demo(cq: CallbackQuery):
    st.demo = not st.demo
    st.save()
    await cq.answer(f"Режим: {'Demo 🎭' if st.demo else 'Live 🌐'}")
    await cq.message.edit_reply_markup(reply_markup=main_kb())


@router.callback_query(F.data == "filters")
async def cb_filters(cq: CallbackQuery):
    await cq.answer()
    await cq.message.edit_text("⚙️ <b>Фильтры</b>", reply_markup=filters_kb(), parse_mode=ParseMode.HTML)


@router.callback_query(F.data == "f_bb")
async def cb_fbb(cq: CallbackQuery):
    "basketball" in st.sports and st.sports.discard("basketball") or st.sports.add("basketball")
    st.save(); await cq.answer(); await cq.message.edit_reply_markup(reply_markup=filters_kb())


@router.callback_query(F.data == "f_vb")
async def cb_fvb(cq: CallbackQuery):
    "volleyball" in st.sports and st.sports.discard("volleyball") or st.sports.add("volleyball")
    st.save(); await cq.answer(); await cq.message.edit_reply_markup(reply_markup=filters_kb())


@router.callback_query(F.data == "p_minus")
async def cb_pminus(cq: CallbackQuery):
    st.min_profit = max(0.1, round(st.min_profit - 0.5, 1))
    st.save(); await cq.answer(f"{st.min_profit}%"); await cq.message.edit_reply_markup(reply_markup=filters_kb())


@router.callback_query(F.data == "p_plus")
async def cb_pplus(cq: CallbackQuery):
    st.min_profit = round(st.min_profit + 0.5, 1)
    st.save(); await cq.answer(f"{st.min_profit}%"); await cq.message.edit_reply_markup(reply_markup=filters_kb())


@router.callback_query(F.data == "stats")
async def cb_stats(cq: CallbackQuery):
    await cq.answer()
    bb = sum(1 for c in st.last if c.sport == "basketball")
    vb = sum(1 for c in st.last if c.sport == "volleyball")
    live = sum(1 for c in st.last if c.is_live)
    await cq.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"🔄 Сканирований: <b>{st.scans}</b>\n"
        f"⏱ Последнее: <b>{st.last_time}</b>\n"
        f"💰 Найдено всего: <b>{st.found}</b>\n\n"
        f"🏀 Баскетбол: <b>{bb}</b>\n"
        f"🏐 Волейбол: <b>{vb}</b>\n"
        f"🔴 Live: <b>{live}</b>\n\n"
        f"⚙️ Режим: {'Demo' if st.demo else 'Live'}\n"
        f"💰 Мин. профит: {st.min_profit}%",
        reply_markup=back_kb(), parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data == "help")
async def cb_help(cq: CallbackQuery):
    await cq.answer()
    await cq.message.edit_text(
        "ℹ️ <b>Как работает</b>\n\n"
        "<b>Веб-дашборд (рекомендуется):</b>\n"
        "Запросы к API Fonbet/Maxline идут <b>прямо из браузера</b> пользователя через Telegram Mini App. "
        "Никакого сервера-посредника — без прокси, без блокировок.\n\n"
        "<b>Серверный режим:</b>\n"
        "Бот делает запросы со своего IP. Может потребоваться прокси.\n\n"
        "<b>Формула коридора:</b>\n"
        "<code>margin = 1/k1 + 1/k2 &lt; 1</code>\n"
        "<code>profit = (1/margin − 1) × 100%</code>\n\n"
        "⚠️ <i>Только для ознакомительных целей.</i>",
        reply_markup=back_kb(), parse_mode=ParseMode.HTML
    )


@router.callback_query(F.data == "noop")
async def cb_noop(cq: CallbackQuery):
    await cq.answer()


# ─────────────────────────────────────────────
# SCAN LOGIC
# ─────────────────────────────────────────────
async def run_scan_and_reply(target: Message):
    msg = await target.answer("⏳ Сканирую...")
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
            "💡 Снизьте мин. профит или переключитесь в Demo-режим.",
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


async def do_scan() -> list[Corridor]:
    scanner = CorridorScanner(demo_mode=st.demo)
    corridors = await scanner.scan_all()
    return [c for c in corridors
            if c.sport in st.sports and c.profit_percent >= st.min_profit]


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
                hdr = (f"🔔 <b>Коридоры!</b> [{st.last_time}]\n"
                       f"Найдено: <b>{len(corridors)}</b>")
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

    # Устанавливаем кнопку меню с Mini App
    if not WEBAPP_URL.startswith("https://YOUR"):
        try:
            await bot.set_chat_menu_button(
                menu_button=MenuButtonWebApp(
                    text="📊 Дашборд",
                    web_app=WebAppInfo(url=WEBAPP_URL)
                )
            )
            logger.info(f"Mini App кнопка установлена: {WEBAPP_URL}")
        except Exception as e:
            logger.warning(f"Не удалось установить меню-кнопку: {e}")

    await bot.set_my_commands([
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="scan", description="Сканировать"),
        BotCommand(command="webapp", description="Открыть веб-дашборд"),
        BotCommand(command="help", description="Помощь"),
    ])

    logger.info(f"Бот запущен | Demo={st.demo} | Подписчиков={len(st.subscribers)}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
