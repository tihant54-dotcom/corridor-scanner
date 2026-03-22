"""
Парсер коридоров для Fonbet и Maxline
Баскетбол и Волейбол
"""
import asyncio
import aiohttp
import logging
import re
import json
import random
from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime
from difflib import SequenceMatcher

import config

logger = logging.getLogger(__name__)


@dataclass
class Market:
    """Котировка (тотал/фора)"""
    type: str          # "total_over", "total_under", "handicap1", "handicap2"
    line: float        # значение линии (напр. 152.5)
    odds: float        # коэффициент
    bookmaker: str
    period: str = "fulltime"  # "fulltime", "1h", "2h", "q1", etc.


@dataclass
class Event:
    """Спортивное событие"""
    id: str
    sport: str
    league: str
    home: str
    away: str
    start_time: str
    bookmaker: str
    markets: list[Market] = field(default_factory=list)
    is_live: bool = False
    score: str = ""


@dataclass
class Corridor:
    """Найденный коридор"""
    sport: str
    home: str
    away: str
    league: str
    start_time: str
    corridor_type: str      # "total", "handicap"
    line: float
    period: str
    bk1_name: str
    bk1_type: str           # "over" / "handicap1"
    bk1_odds: float
    bk2_name: str
    bk2_type: str           # "under" / "handicap2"
    bk2_odds: float
    profit_percent: float
    is_live: bool
    score: str
    found_at: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

    def to_message(self) -> str:
        sport_emoji = {"basketball": "🏀", "volleyball": "🏐"}.get(self.sport, "⚽")
        live_tag = f"🔴 LIVE {self.score}" if self.is_live else "📅 Линия"
        period_map = {"fulltime": "Матч", "1h": "1-я четверть/сет", "2h": "2-я четверть/сет",
                      "q1": "1Q", "q2": "2Q", "q3": "3Q", "q4": "4Q"}
        period_str = period_map.get(self.period, self.period)

        type_str = "Тотал" if self.corridor_type == "total" else "Фора"
        sign1 = "ТБ" if self.bk1_type == "over" else ("ТМ" if self.bk1_type == "under" else "Ф1")
        sign2 = "ТМ" if self.bk2_type == "under" else ("ТБ" if self.bk2_type == "over" else "Ф2")

        return (
            f"{sport_emoji} <b>{self.home} — {self.away}</b>\n"
            f"🏆 {self.league}\n"
            f"⏱ {live_tag} | {period_str}\n"
            f"─────────────────────\n"
            f"📊 <b>Коридор {type_str} {self.line}</b>\n"
            f"• {self.bk1_name}: {sign1} {self.line} @ <b>{self.bk1_odds}</b>\n"
            f"• {self.bk2_name}: {sign2} {self.line} @ <b>{self.bk2_odds}</b>\n"
            f"─────────────────────\n"
            f"💰 <b>Профит: {self.profit_percent:.2f}%</b>\n"
            f"🕐 {self.found_at}"
        )

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────
# FONBET PARSER
# ─────────────────────────────────────────────
class FonbetParser:
    NAME = "Fonbet"
    BASE = "https://sports.fonbet.ru"
    API_LIVE = "https://sports.fonbet.ru/live/data"
    API_LINE = "https://sports.fonbet.ru/line/data"

    SPORT_IDS = {"basketball": 3, "volleyball": 5}

    PERIOD_MAP = {
        # баскетбол
        "1": "fulltime", "2": "1h", "3": "2h",
        "4": "q1", "5": "q2", "6": "q3", "7": "q4",
        # волейбол
        "1001": "fulltime", "1002": "s1", "1003": "s2", "1004": "s3",
    }

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch(self, url: str, params: dict = None) -> dict | None:
        try:
            async with self.session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    return await r.json(content_type=None)
        except Exception as e:
            logger.warning(f"Fonbet fetch error: {e}")
        return None

    async def get_events(self, sport: str, live: bool = True) -> list[Event]:
        sport_id = self.SPORT_IDS.get(sport)
        if not sport_id:
            return []

        url = self.API_LIVE if live else self.API_LINE
        params = {"sportId": sport_id, "lang": "ru"}
        data = await self.fetch(url, params)
        if not data:
            return []

        events = []
        for raw in data.get("events", []):
            try:
                event = self._parse_event(raw, sport, live)
                if event:
                    events.append(event)
            except Exception as e:
                logger.debug(f"Fonbet event parse error: {e}")

        logger.info(f"Fonbet {sport} {'live' if live else 'line'}: {len(events)} events")
        return events

    def _parse_event(self, raw: dict, sport: str, live: bool) -> Optional[Event]:
        home = raw.get("team1", {}).get("name", "")
        away = raw.get("team2", {}).get("name", "")
        if not home or not away:
            return None

        event = Event(
            id=str(raw.get("id", "")),
            sport=sport,
            league=raw.get("competition", {}).get("name", ""),
            home=home,
            away=away,
            start_time=raw.get("startTime", ""),
            bookmaker=self.NAME,
            is_live=live,
            score=self._parse_score(raw),
        )

        # Парсим тоталы и форы
        for factor_row in raw.get("factors", []):
            market = self._parse_factor(factor_row)
            if market:
                event.markets.append(market)

        return event if event.markets else None

    def _parse_score(self, raw: dict) -> str:
        score = raw.get("score", {})
        if score:
            return f"{score.get('team1', 0)}:{score.get('team2', 0)}"
        return ""

    def _parse_factor(self, factor: dict) -> Optional[Market]:
        ftype = str(factor.get("factorType", ""))
        period = self.PERIOD_MAP.get(str(factor.get("period", "1")), "fulltime")
        odds = float(factor.get("factor", 0))

        if odds < 1.01:
            return None

        # Тотал больше
        if ftype in ("over_total", "total_over", "TB"):
            line = float(factor.get("param", 0))
            return Market("total_over", line, odds, self.NAME, period)

        # Тотал меньше
        if ftype in ("under_total", "total_under", "TM"):
            line = float(factor.get("param", 0))
            return Market("total_under", line, odds, self.NAME, period)

        # Фора 1
        if ftype in ("handicap1", "F1", "h1"):
            line = float(factor.get("param", 0))
            return Market("handicap1", line, odds, self.NAME, period)

        # Фора 2
        if ftype in ("handicap2", "F2", "h2"):
            line = float(factor.get("param", 0))
            return Market("handicap2", line, odds, self.NAME, period)

        return None


# ─────────────────────────────────────────────
# MAXLINE PARSER
# ─────────────────────────────────────────────
class MaxlineParser:
    NAME = "Maxline"
    API_LIVE = "https://www.maxline.by/api/live/events"
    API_LINE = "https://www.maxline.by/api/prematch/events"

    SPORT_IDS = {"basketball": 2, "volleyball": 6}

    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def fetch(self, url: str, params: dict = None) -> dict | None:
        try:
            headers = {**config.HEADERS, "Referer": "https://www.maxline.by/"}
            async with self.session.get(url, params=params, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status == 200:
                    return await r.json(content_type=None)
        except Exception as e:
            logger.warning(f"Maxline fetch error: {e}")
        return None

    async def get_events(self, sport: str, live: bool = True) -> list[Event]:
        sport_id = self.SPORT_IDS.get(sport)
        if not sport_id:
            return []

        url = self.API_LIVE if live else self.API_LINE
        params = {"sportId": sport_id}
        data = await self.fetch(url, params)
        if not data:
            return []

        events = []
        for raw in data.get("items", data.get("events", [])):
            try:
                event = self._parse_event(raw, sport, live)
                if event:
                    events.append(event)
            except Exception as e:
                logger.debug(f"Maxline event parse error: {e}")

        logger.info(f"Maxline {sport} {'live' if live else 'line'}: {len(events)} events")
        return events

    def _parse_event(self, raw: dict, sport: str, live: bool) -> Optional[Event]:
        # Maxline структура может отличаться
        competitors = raw.get("competitors", raw.get("teams", []))
        if len(competitors) < 2:
            return None

        home = competitors[0].get("name", "")
        away = competitors[1].get("name", "")

        event = Event(
            id=str(raw.get("id", raw.get("eventId", ""))),
            sport=sport,
            league=raw.get("competitionName", raw.get("league", {}).get("name", "")),
            home=home,
            away=away,
            start_time=raw.get("kickoff", raw.get("startTime", "")),
            bookmaker=self.NAME,
            is_live=live,
            score=self._parse_score(raw),
        )

        for market in raw.get("markets", raw.get("odds", [])):
            parsed = self._parse_market(market)
            if parsed:
                event.markets.append(parsed)

        return event if event.markets else None

    def _parse_score(self, raw: dict) -> str:
        score = raw.get("score", raw.get("liveScore", {}))
        if isinstance(score, dict):
            return f"{score.get('home', 0)}:{score.get('away', 0)}"
        if isinstance(score, str):
            return score
        return ""

    def _parse_market(self, market: dict) -> Optional[Market]:
        mname = market.get("name", market.get("type", "")).lower()
        period = "fulltime"
        if "1-я" in mname or "1h" in mname or "1 пол" in mname:
            period = "1h"
        elif "2-я" in mname or "2h" in mname:
            period = "2h"

        odds = float(market.get("odds", market.get("value", 0)))
        if odds < 1.01:
            return None

        line = float(market.get("param", market.get("handicap", market.get("total", 0))))

        if "тб" in mname or "больше" in mname or "over" in mname:
            return Market("total_over", line, odds, self.NAME, period)
        if "тм" in mname or "меньше" in mname or "under" in mname:
            return Market("total_under", line, odds, self.NAME, period)
        if "ф1" in mname or "handicap1" in mname or "фора 1" in mname:
            return Market("handicap1", line, odds, self.NAME, period)
        if "ф2" in mname or "handicap2" in mname or "фора 2" in mname:
            return Market("handicap2", line, odds, self.NAME, period)

        return None


# ─────────────────────────────────────────────
# ГЕНЕРАТОР ДЕМО-ДАННЫХ (если API недоступен)
# ─────────────────────────────────────────────
class DemoDataGenerator:
    """Генерирует реалистичные тестовые данные"""

    BASKETBALL_LEAGUES = ["NBA", "Евролига", "VTB United League", "Turkish BSL", "Panathinaikos"]
    VOLLEYBALL_LEAGUES = ["VNL", "CEV Champions League", "Суперлига Россия", "PlusLiga", "Serie A1"]

    BB_TEAMS = [
        ("Бостон Селтикс", "Лос-Анджелес Лейкерс"), ("ЦСКА", "Реал Мадрид"),
        ("Фенербахче", "Олимпиакос"), ("Зенит", "УНИКС"), ("Химки", "Локомотив-Кубань"),
        ("Milwaukee Bucks", "Golden State Warriors"), ("Brooklyn Nets", "Chicago Bulls"),
        ("Барселона", "Альба Берлин"), ("Маккаби", "Партизан"),
    ]
    VB_TEAMS = [
        ("Зенит Казань", "Белогорье"), ("СКРА", "Ресовия"), ("Тренто", "Перуджа"),
        ("Белогорье", "Факел"), ("Динамо", "Локомотив"), ("Сборная Польша", "Сборная Франция"),
        ("Модена", "Сир Сейфти Коньяалты"), ("Кузбасс", "Нефтяник"),
    ]

    @classmethod
    def generate_events(cls, sport: str, bookmaker: str, live: bool = True) -> list[Event]:
        teams_list = cls.BB_TEAMS if sport == "basketball" else cls.VB_TEAMS
        leagues = cls.BASKETBALL_LEAGUES if sport == "basketball" else cls.VOLLEYBALL_LEAGUES

        events = []
        count = random.randint(4, 8)
        selected = random.sample(teams_list, min(count, len(teams_list)))

        for home, away in selected:
            total_base = 155.5 if sport == "basketball" else 48.5
            total = total_base + random.choice([-5, -2.5, 0, 2.5, 5])

            # Небольшое смещение котировок между БК
            offset = random.uniform(-0.06, 0.06)

            markets = [
                Market("total_over", total, round(random.uniform(1.80, 1.95) + offset, 2), bookmaker, "fulltime"),
                Market("total_under", total, round(random.uniform(1.80, 1.95) - offset, 2), bookmaker, "fulltime"),
                Market("total_over", total - 2.5, round(random.uniform(1.70, 1.85), 2), bookmaker, "fulltime"),
                Market("total_under", total + 2.5, round(random.uniform(1.70, 1.85), 2), bookmaker, "fulltime"),
            ]

            if sport == "basketball":
                # Добавим квартальные тоталы
                q_total = total / 4
                markets += [
                    Market("total_over", round(q_total, 1), round(random.uniform(1.75, 1.95), 2), bookmaker, "q1"),
                    Market("total_under", round(q_total, 1), round(random.uniform(1.75, 1.95), 2), bookmaker, "q1"),
                ]

            event = Event(
                id=f"demo_{sport}_{home}_{bookmaker}",
                sport=sport,
                league=random.choice(leagues),
                home=home,
                away=away,
                start_time=datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                bookmaker=bookmaker,
                markets=markets,
                is_live=live,
                score=f"{random.randint(0, 80)}:{random.randint(0, 80)}" if live and sport == "basketball"
                      else f"{random.randint(0, 3)}:{random.randint(0, 3)}" if live else "",
            )
            events.append(event)

        return events


# ─────────────────────────────────────────────
# ДВИЖОК ПОИСКА КОРИДОРОВ
# ─────────────────────────────────────────────
class CorridorFinder:
    def __init__(self):
        self._seen: set[str] = set()

    def find_corridors(self, fonbet_events: list[Event], maxline_events: list[Event]) -> list[Corridor]:
        corridors = []
        matches = self._match_events(fonbet_events, maxline_events)

        for fb_event, ml_event in matches:
            found = self._compare_markets(fb_event, ml_event)
            corridors.extend(found)

        return corridors

    def _match_events(self, ev1: list[Event], ev2: list[Event]) -> list[tuple[Event, Event]]:
        pairs = []
        for e1 in ev1:
            best_match = None
            best_score = config.FUZZY_THRESHOLD / 100

            for e2 in ev2:
                score = self._team_similarity(e1.home, e1.away, e2.home, e2.away)
                if score > best_score:
                    best_score = score
                    best_match = e2

            if best_match:
                pairs.append((e1, best_match))
        return pairs

    def _team_similarity(self, h1, a1, h2, a2) -> float:
        def sim(s1, s2):
            s1, s2 = s1.lower().strip(), s2.lower().strip()
            return SequenceMatcher(None, s1, s2).ratio()

        direct = (sim(h1, h2) + sim(a1, a2)) / 2
        reverse = (sim(h1, a2) + sim(a1, h2)) / 2
        return max(direct, reverse)

    def _compare_markets(self, e1: Event, e2: Event) -> list[Corridor]:
        corridors = []

        # Группируем рынки по типу и периоду
        def group(event: Event) -> dict:
            g = {}
            for m in event.markets:
                key = (m.period, m.line)
                g.setdefault(key, []).append(m)
            return g

        g1 = group(e1)
        g2 = group(e2)

        all_keys = set(g1.keys()) | set(g2.keys())

        for key in all_keys:
            markets1 = g1.get(key, [])
            markets2 = g2.get(key, [])

            # Ищем тотал-коридоры
            overs1 = [m for m in markets1 if m.type == "total_over"]
            unders1 = [m for m in markets1 if m.type == "total_under"]
            overs2 = [m for m in markets2 if m.type == "total_over"]
            unders2 = [m for m in markets2 if m.type == "total_under"]

            # Fonbet ТБ + Maxline ТМ
            for ov in overs1:
                for un in unders2:
                    if ov.line == un.line:
                        corridor = self._calc_corridor(
                            e1, ov, e2, un, "total"
                        )
                        if corridor:
                            corridors.append(corridor)

            # Maxline ТБ + Fonbet ТМ
            for ov in overs2:
                for un in unders1:
                    if ov.line == un.line:
                        corridor = self._calc_corridor(
                            e2, ov, e1, un, "total"
                        )
                        if corridor:
                            corridors.append(corridor)

        return corridors

    def _calc_corridor(self, ev1: Event, m1: Market, ev2: Event, m2: Market, ctype: str) -> Optional[Corridor]:
        """
        Коридор: ставим 1 единицу на каждую котировку.
        Профит = (k1 + k2 - 2) / 2 * 100%  (упрощённая формула для равных ставок)
        Или точнее: оптимальные ставки s1, s2 при которых гарантируем профит.
        """
        k1, k2 = m1.odds, m2.odds

        # Ставки при равном риске $100
        # s1 = 100 / k1, s2 = 100 / k2
        # margin = 1/k1 + 1/k2
        margin = 1 / k1 + 1 / k2

        if margin >= 1.0:
            return None  # Нет арба

        profit_pct = (1 / margin - 1) * 100

        if not (config.MIN_CORRIDOR_PROFIT <= profit_pct <= config.MAX_CORRIDOR_PROFIT):
            return None

        # Дедупликация
        uid = f"{ev1.home}_{ev1.away}_{m1.line}_{m1.period}_{ctype}"
        if uid in self._seen:
            return None
        self._seen.add(uid)

        return Corridor(
            sport=ev1.sport,
            home=ev1.home,
            away=ev1.away,
            league=ev1.league or ev2.league,
            start_time=ev1.start_time,
            corridor_type=ctype,
            line=m1.line,
            period=m1.period,
            bk1_name=m1.bookmaker,
            bk1_type="over" if m1.type == "total_over" else "under",
            bk1_odds=k1,
            bk2_name=m2.bookmaker,
            bk2_type="under" if m2.type == "total_under" else "over",
            bk2_odds=k2,
            profit_percent=round(profit_pct, 2),
            is_live=ev1.is_live or ev2.is_live,
            score=ev1.score or ev2.score,
        )


# ─────────────────────────────────────────────
# ГЛАВНЫЙ СКАНЕР
# ─────────────────────────────────────────────
class CorridorScanner:
    def __init__(self, demo_mode: bool = False):
        self.demo_mode = demo_mode
        self.finder = CorridorFinder()

    async def scan_all(self) -> list[Corridor]:
        all_corridors = []

        async with aiohttp.ClientSession(headers=config.HEADERS) as session:
            fonbet = FonbetParser(session)
            maxline = MaxlineParser(session)

            for sport in config.SPORTS:
                for live in (True, False):
                    mode = "live" if live else "line"
                    try:
                        if self.demo_mode:
                            fb_events = DemoDataGenerator.generate_events(sport, "Fonbet", live)
                            ml_events = DemoDataGenerator.generate_events(sport, "Maxline", live)
                        else:
                            fb_events = await fonbet.get_events(sport, live)
                            ml_events = await maxline.get_events(sport, live)

                        corridors = self.finder.find_corridors(fb_events, ml_events)
                        all_corridors.extend(corridors)
                        logger.info(f"[{sport}/{mode}] Найдено коридоров: {len(corridors)}")

                    except Exception as e:
                        logger.error(f"Scan error [{sport}/{mode}]: {e}")

        return sorted(all_corridors, key=lambda c: c.profit_percent, reverse=True)


# ─────────────────────────────────────────────
# CLI ТЕСТ
# ─────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    async def main():
        scanner = CorridorScanner(demo_mode=True)
        corridors = await scanner.scan_all()

        if corridors:
            print(f"\n{'='*50}")
            print(f"  Найдено коридоров: {len(corridors)}")
            print(f"{'='*50}\n")
            for c in corridors:
                print(c.to_message().replace("<b>", "").replace("</b>", ""))
                print()
        else:
            print("Коридоров не найдено.")

    asyncio.run(main())
