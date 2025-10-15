import datetime as dt
import json
from typing import Dict, Any, List, Tuple

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from mm08.models import Instrument, Candle

from django.utils import timezone
from zoneinfo import ZoneInfo
MSK_TZ = ZoneInfo("Europe/Moscow")


ISS_BASE = "https://iss.moex.com/iss"
USER_AGENT = "Django-MM08/1.0 (+https://example.local)"


def fetch_candles(engine: str, market: str, board: str, ticker: str,
                  date_from: str, date_till: str, interval: int) -> List[Dict[str, Any]]:
    """
    Тянем свечи из ISS (candles.json) с пагинацией по &start=.
    Возвращаем список dict по колонкам.
    """
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    all_rows: List[Dict[str, Any]] = []
    start = 0

    # Пример: /iss/engines/stock/markets/shares/boards/TQBR/securities/SBER/candles.json
    url = (
        f"{ISS_BASE}/engines/{engine}/markets/{market}/boards/{board}/"
        f"securities/{ticker}/candles.json"
    )

    params = {
        "from": date_from,
        "till": date_till,
        "interval": interval,
        "start": start,
    }

    while True:
        params["start"] = start
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # таблица 'candles' -> columns + data
        if "candles" not in data:
            break

        columns = data["candles"]["columns"]
        rows = data["candles"]["data"] or []
        if not rows:
            break

        for row in rows:
            obj = dict(zip(columns, row))
            all_rows.append(obj)

        # пагинация
        # если вернули меньше 100 строк, значит достигли конца
        if len(rows) < 100:
            break

        start += len(rows)

    return all_rows


def ensure_instrument(ticker: str, defaults: Dict[str, Any]) -> Instrument:
    inst, _ = Instrument.objects.get_or_create(ticker=ticker, defaults=defaults)
    # обновим поля, если поменялись (удобно при повторных вызовах)
    updated = False
    for f, v in defaults.items():
        if getattr(inst, f) != v:
            setattr(inst, f, v)
            updated = True
    if updated:
        inst.save(update_fields=list(defaults.keys()))
    return inst


class Command(BaseCommand):
    help = "Загрузка свечей с MOEX ISS в таблицу Candle"

    def add_arguments(self, parser):
        parser.add_argument("--ticker", required=True, help="Напр., SBER / GAZP / USDRUBF")
        parser.add_argument("--engine", default="stock", help="stock|futures|currency|index ...")
        parser.add_argument("--market", default="shares", help="shares|futures|bonds ...")
        parser.add_argument("--board", default="TQBR", help="TQBR|RFUD|...")

        parser.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
        parser.add_argument("--to", dest="date_till", required=True, help="YYYY-MM-DD")

        parser.add_argument("--interval", type=int, default=60,
                            help="1, 10, 60, 1440 (см. модель Candle.Interval)")

        parser.add_argument("--shortname", default="", help="Читаемое имя инструмента")
        parser.add_argument("--lot", type=int, default=1, help="Размер лота")

    @transaction.atomic
    def handle(self, *args, **options):
        ticker = options["ticker"].upper()
        engine = options["engine"]
        market = options["market"]
        board = options["board"]
        date_from = options["date_from"]
        date_till = options["date_till"]
        interval = int(options["interval"])

        # валидация дат
        try:
            _ = dt.date.fromisoformat(date_from)
            _ = dt.date.fromisoformat(date_till)
        except ValueError:
            raise CommandError("Неверный формат даты. Ожидается YYYY-MM-DD.")

        inst = ensure_instrument(
            ticker,
            defaults=dict(
                secid=ticker,
                shortname=options["shortname"],
                engine=engine,
                market=market,
                board=board,
                lot_size=options["lot"],
                is_active=True,
            ),
        )

        self.stdout.write(self.style.NOTICE(
            f"Загружаю свечи: {ticker} | {engine}/{market}/{board} | {date_from}..{date_till} | interval={interval}"
        ))

        rows = fetch_candles(engine, market, board, ticker, date_from, date_till, interval)
        if not rows:
            self.stdout.write(self.style.WARNING("Данных не найдено."))
            return

        created, updated = 0, 0
        for r in rows:
            # columns: begin, end, open, close, high, low, value, volume
            dt_begin = r.get("begin")  # e.g. "2025-01-10 10:00:00"
            if not dt_begin:
                continue

            # 1) парсим как "наивное" локальное MSK-время
            dt_local = dt.datetime.fromisoformat(dt_begin)
            if timezone.is_naive(dt_local):
                dt_local = dt_local.replace(tzinfo=MSK_TZ)

            # 2) приводим к UTC для хранения при USE_TZ=True
            dt_utc = dt_local.astimezone(timezone.utc)

            obj, is_created = Candle.objects.update_or_create(
                instrument=inst, dt=dt_utc, interval=interval,
                defaults=dict(
                    open=r.get("open") or 0.0,
                    high=r.get("high") or 0.0,
                    low=r.get("low") or 0.0,
                    close=r.get("close") or 0.0,
                    volume=int(r.get("volume") or 0),
                )
            )
            if is_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Готово: создано {created}, обновлено {updated}, всего {created+updated}"
        ))
