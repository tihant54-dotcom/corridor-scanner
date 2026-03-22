import os

# ========================
# TELEGRAM BOT
# ========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
CHAT_IDS = []  # список chat_id для уведомлений

# ========================
# ПАРСИНГ
# ========================
PARSE_INTERVAL = 30  # секунд между проверками
MIN_CORRIDOR_PROFIT = 0.5  # минимальный % профита коридора
MAX_CORRIDOR_PROFIT = 20.0  # максимальный % (слишком высокий = ошибка)

# Спорты для мониторинга
SPORTS = ["basketball", "volleyball"]

# ========================
# БУКМЕКЕРЫ
# ========================
FONBET_API = "https://sports.fonbet.ru/live/data"
FONBET_SPORT_IDS = {
    "basketball": 3,
    "volleyball": 5,
}

MAXLINE_API = "https://www.maxline.by/api/events"
MAXLINE_SPORT_IDS = {
    "basketball": 2,
    "volleyball": 6,
}

# Headers для запросов
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
    "Referer": "https://fonbet.ru/",
}

# Прокси (опционально)
PROXIES = None
# PROXIES = {"http": "http://user:pass@proxy:port", "https": "http://user:pass@proxy:port"}

# ========================
# МАТЧИНГ КОМАНД
# ========================
FUZZY_THRESHOLD = 75  # порог схожести названий команд (0-100)

# ========================
# ЛОГИРОВАНИЕ
# ========================
LOG_LEVEL = "INFO"
LOG_FILE = "corridor.log"
