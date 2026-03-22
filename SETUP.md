# 🚀 БЫСТРЫЙ ЗАПУСК

## Архитектура — почему без прокси

```
Пользователь открывает Mini App в Telegram
       ↓
Браузер Telegram делает fetch() к fonbet.ru / maxline.by
       ↓
Запросы идут с IP пользователя — не с сервера бота
       ↓
Никаких блокировок, никаких прокси!
```

---

## Шаг 1 — Залить miniapp.html на хостинг

Нужен **HTTPS**. Бесплатные варианты:

### Вариант A: GitHub Pages (рекомендуется, 5 минут)
```bash
# 1. Создайте репозиторий на github.com
# 2. Загрузите miniapp.html → переименуйте в index.html
# 3. Settings → Pages → Deploy from branch → main
# 4. URL будет: https://USERNAME.github.io/REPO/
```

### Вариант B: Netlify (drag & drop)
```
1. Зайдите на netlify.com
2. Перетащите miniapp.html в браузер
3. Получите URL вида: https://RANDOM.netlify.app
```

### Вариант C: Vercel
```bash
npm i -g vercel
vercel miniapp.html
# → https://RANDOM.vercel.app
```

---

## Шаг 2 — Настроить бота

### 2.1 — Токен бота
```bash
# .env файл или переменная окружения:
export BOT_TOKEN="1234567890:ABCdef..."
export WEBAPP_URL="https://YOUR_DOMAIN/miniapp.html"
```

Или в `config.py`:
```python
BOT_TOKEN = "1234567890:ABCdef..."
```

### 2.2 — Разрешить домен в BotFather
```
/newapp → выберите вашего бота
Или используйте встроенную кнопку Web App
```

---

## Шаг 3 — Установить зависимости и запустить

```bash
pip install -r requirements.txt
python bot.py
```

---

## Файлы

| Файл | Назначение |
|------|-----------|
| `miniapp.html` | Веб-дашборд (Telegram Mini App) |
| `bot.py` | Telegram-бот |
| `parser.py` | Парсер + движок коридоров |
| `config.py` | Настройки |

---

## Как это работает технически

### Без прокси (через Mini App)
1. Пользователь нажимает кнопку "Открыть дашборд" в боте
2. Telegram открывает встроенный браузер с `miniapp.html`
3. JavaScript внутри страницы делает `fetch()` к API Fonbet/Maxline
4. Запросы идут с IP пользователя → без блокировок

### С сервером (Demo/Live режим в боте)
1. Бот делает запросы со своего IP
2. Если сервер в РФ/РБ — обычно работает без прокси
3. Если VPS за рубежом — может потребоваться прокси

---

## CORS-проблема

Если браузер блокирует запросы (CORS), в `miniapp.html` есть авто-fallback на демо-данные.
Для обхода CORS можно использовать публичный прокси:

```javascript
// В miniapp.html замените CORS_PROXY на:
const CORS_PROXY = 'https://corsproxy.io/?';
// И URL будет:
const url = CORS_PROXY + encodeURIComponent(originalUrl);
```

---

## Переменные окружения

```bash
BOT_TOKEN=       # Токен от @BotFather (обязательно)
WEBAPP_URL=      # HTTPS URL вашего miniapp.html
PARSE_INTERVAL=  # Интервал авто-скана в секундах (по умолчанию 30)
```
