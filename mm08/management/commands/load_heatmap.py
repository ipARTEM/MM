# mm08/management/commands/load_heatmap.py
from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mm08.models import HeatSnapshot, HeatTile


# ---- Конфиг путей ISS по борду -------------------------------------------------

def resolve_path(board: str) -> tuple[str, str, str]:
    """
    Вернёт (engine, market, url_template) для указанного board.
    По умолчанию считаем, что это акции (stock/shares).
    """
    b = board.upper()

    # Фьючерсы (FORTS)
    if b.startswith("RF"):
        return (
            "futures",
            "forts",
            "https://iss.moex.com/iss/engines/futures/markets/forts/boards/{board}/securities.json",
        )

    # Акции (T+)
    return (
        "stock",
        "shares",
        "https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities.json",
    )


# ---- Вспомогательные функции ----------------------------------------------------

def _to_decimal(x):
    if x in (None, "", "-"):
        return None
    try:
        return Decimal(str(x))
    except InvalidOperation:
        return None


def _rows_from_table(tbl) -> list[dict]:
    """
    Унифицируем таблицу ISS в список словарей.
    Поддерживает:
      - {"columns":[...], "data":[[...], ...]}
      - [{"SECID": "...", ...}, ...]
    """
    if not tbl:
        return []

    # Уже список словарей
    if isinstance(tbl, list):
        if tbl and isinstance(tbl[0], dict):
            return tbl
        return []

    # Классическая форма
    cols = tbl.get("columns") or []
    data = tbl.get("data") or []
    out = []
    for row in data:
        d = {}
        for i, col in enumerate(cols):
            if i < len(row):
                d[col] = row[i]
        out.append(d)
    return out


def fetch_board(board: str) -> tuple[str, str, list[dict]]:
    """
    Возвращает (engine, market, rows) для выбранного board.
    rows = [{ticker, shortname, lot_size, last, change_pct, turnover, volume}, ...]
    """
    engine, market, URL = resolve_path(board)

    # Берём побольше полей — они есть и у акций, и у фьючерсов
    SEC_COLS = "SECID,SHORTNAME,LOTSIZE"
    MD_COLS = (
        "SECID,LAST,OPEN,PREVPRICE,CHANGE,LASTCHANGEPRC,VALTODAY,VOLTODAY,NUMTRADES"
    )

    params = {
        "iss.only": "securities,marketdata",
        "iss.meta": "off",
        "iss.json": "extended",
        "securities.columns": SEC_COLS,
        "marketdata.columns": MD_COLS,
    }

    r = requests.get(URL.format(board=board), params=params, timeout=20)
    r.raise_for_status()
    raw = r.json()

    # Найдём нужные таблицы вне зависимости от формы
    securities_tbl = None
    marketdata_tbl = None
    if isinstance(raw, dict):
        securities_tbl = raw.get("securities")
        marketdata_tbl = raw.get("marketdata")
    elif isinstance(raw, list):
        for part in raw:
            if isinstance(part, dict):
                securities_tbl = part.get("securities", securities_tbl)
                marketdata_tbl = part.get("marketdata", marketdata_tbl)

    sec_rows = _rows_from_table(securities_tbl)
    md_rows = _rows_from_table(marketdata_tbl)

    md_by_secid = {
        row.get("SECID"): row for row in md_rows if isinstance(row, dict) and row.get("SECID")
    }

    rows = []
    for s in sec_rows:
        secid = s.get("SECID")
        if not secid:
            continue
        m = md_by_secid.get(secid) or {}

        last = _to_decimal(m.get("LAST"))
        prev = _to_decimal(m.get("PREVPRICE"))
        chg = _to_decimal(m.get("CHANGE"))
        ready_pct = _to_decimal(m.get("LASTCHANGEPRC"))

        # Правильный %: сначала пробуем готовый от МОЕХ
        change_pct = ready_pct
        if change_pct is None:
            # Пытаемся посчитать из CHANGE/PREVPRICE
            if chg is not None and prev not in (None, Decimal("0")):
                change_pct = (chg / prev) * Decimal("100")
            # Или из LAST/PREVPRICE
            elif last is not None and prev not in (None, Decimal("0")):
                change_pct = ((last - prev) / prev) * Decimal("100")

        # Оборот/объём — что найдём
        turnover = m.get("VALTODAY") or m.get("VOLTODAY") or 0
        volume = m.get("NUMTRADES") or 0

        rows.append(
            {
                "ticker": secid,
                "shortname": s.get("SHORTNAME") or "",
                "lot_size": int(s.get("LOTSIZE") or 1),
                "last": float(last) if last is not None else 0.0,
                "change_pct": float(change_pct) if change_pct is not None else None,
                "turnover": int(turnover or 0),
                "volume": int(volume or 0),
            }
        )

    return engine, market, rows


# ---- Команда --------------------------------------------------------------------

class Command(BaseCommand):
    help = "Загрузить теплокарту MOEX. Пример: load_heatmap --board TQBR --label fast"

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, help="YYYY-MM-DD; по умолчанию сегодня")
        parser.add_argument("--board", type=str, default="TQBR")
        parser.add_argument("--label", type=str, default="fast")

    @transaction.atomic
    def handle(self, *args, **opt):
        board = (opt.get("board") or "TQBR").upper()
        label = (opt.get("label") or "fast").strip()
        date_str = opt.get("date")

        if date_str:
            try:
                d = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                raise CommandError("date должен быть в формате YYYY-MM-DD")
        else:
            d = dt.date.today()

        self.stdout.write(f"Загружаю MOEX heatmap: board={board}, date={d}, label={label}")

        engine, market, rows = fetch_board(board)
        if not rows:
            raise CommandError("MOEX вернул пустые данные.")

        snap, _ = HeatSnapshot.objects.get_or_create(
            date=d, board=board, label=label, defaults={"source": "moex"}
        )
        # Перезапишем плитки
        snap.tiles.all().delete()

        tiles.append(HeatTile(
            snapshot=snap,
            ticker=r["ticker"],
            shortname=r["shortname"],
            engine="stock", market="shares", board=board,
            last=_to_decimal(r["last"]) or Decimal("0"),
            change_pct=_to_decimal(r["change_pct"]),  # ← допускаем None
            turnover=int(r["turnover"] or 0),
            volume=int(r["volume"] or 0),
            lot_size=int(r["lot_size"] or 1),
        ))
        HeatTile.objects.bulk_create(tiles, batch_size=1000)

        self.stdout.write(self.style.SUCCESS(f"OK: {snap} — сохранено {len(tiles)} тикеров."))
