import os
import sys

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
    print("ОШИБКА: BOT_TOKEN не задан в Railway Variables!", file=sys.stderr)
    sys.exit(1)

FORCE_DEMO = os.getenv("DEMO_MODE", "").lower() in ("true", "1", "yes")
CHAT_IDS = []
PARSE_INTERVAL = 30
MIN_CORRIDOR_PROFIT = 0.5
MAX_CORRIDOR_PROFIT = 20.0
SPORTS = ["basketball", "volleyball"]
FONBET_API = "https://sports.fonbet.ru/live/data"
FONBET_SPORT_IDS = {"basketball": 3, "volleyball": 5}
MAXLINE_API = "https://www.maxline.by/api/events"
MAXLINE_SPORT_IDS = {"basketball": 2, "volleyball": 6}
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
    "Referer": "https://fonbet.ru/",
}
PROXIES = None
FUZZY_THRESHOLD = 75
LOG_LEVEL = "INFO"
LOG_FILE = "corridor.log"
