# mm08/management/commands/load_heatmap.py
from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import List, Dict, Tuple, Optional

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mm08.models import HeatSnapshot, HeatTile


# ---------- helpers -------------------------------------------------------------

def resolve_path(board: str) -> tuple[str, str, str]:
    """
    Вернёт (engine, market, url_template) для указанного board.
    RF** -> срочный рынок (FORTS), иначе считаем акции T+.
    """
    b = (board or "").upper()
    if b.startswith("RF"):  # фьючерсы
        return (
            "futures",
            "forts",
            "https://iss.moex.com/iss/engines/futures/markets/forts/boards/{board}/securities.json",
        )
    # акции
    return (
        "stock",
        "shares",
        "https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities.json",
    )


def _to_dec(x: object) -> Optional[Decimal]:
    if x in (None, "", "-", "NaN"):
        return None
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _rows_from_table(tbl) -> List[Dict]:
    """
    Унифицируем таблицу ISS в список словарей.
      - {"columns":[...], "data":[[...], ...]}
      - [{"SECID": "...", ...}, ...]
    """
    if not tbl:
        return []

    if isinstance(tbl, list):
        if tbl and isinstance(tbl[0], dict):
            return tbl
        return []

    cols = tbl.get("columns") or []
    data = tbl.get("data") or []
    out: List[Dict] = []
    for row in data:
        out.append({cols[i]: row[i] for i in range(min(len(cols), len(row)))})
    return out


def fetch_board(board: str) -> Tuple[str, str, List[Dict]]:
    """
    Возвращает (engine, market, rows) для выбранного board.
    rows = [{ticker, shortname, lot_size, last, change_pct, turnover, volume}, ...]
    """
    engine, market, url = resolve_path(board)

    SEC_COLS = "SECID,SHORTNAME,LOTSIZE"
    MD_COLS = "SECID,LAST,OPEN,PREVPRICE,CHANGE,LASTCHANGEPRC,VALTODAY,VOLTODAY,NUMTRADES"

    params = {
        "iss.only": "securities,marketdata",
        "iss.meta": "off",
        "iss.json": "extended",
        "securities.columns": SEC_COLS,
        "marketdata.columns": MD_COLS,
    }

    r = requests.get(url.format(board=board), params=params, timeout=20)
    r.raise_for_status()
    raw = r.json()

    # достаём таблицы вне зависимости от упаковки
    securities_tbl = raw.get("securities") if isinstance(raw, dict) else None
    marketdata_tbl = raw.get("marketdata") if isinstance(raw, dict) else None
    if securities_tbl is None or marketdata_tbl is None:
        if isinstance(raw, list):
            for part in raw:
                if isinstance(part, dict):
                    securities_tbl = securities_tbl or part.get("securities")
                    marketdata_tbl = marketdata_tbl or part.get("marketdata")

    sec_rows = _rows_from_table(securities_tbl)
    md_rows = _rows_from_table(marketdata_tbl)
    md_by_secid = {m.get("SECID"): m for m in md_rows if isinstance(m, dict) and m.get("SECID")}

    rows: List[Dict] = []
    for s in sec_rows:
        secid = (s.get("SECID") or "").strip().upper()
        if not secid:
            continue
        m = md_by_secid.get(secid, {})

        last = _to_dec(m.get("LAST"))
        prev = _to_dec(m.get("PREVPRICE"))
        chg = _to_dec(m.get("CHANGE"))
        ready_pct = _to_dec(m.get("LASTCHANGEPRC"))

        # % изменения: сначала пробуем готовое поле от МОЕХ,
        # иначе считаем сами из CHANGE/PREVPRICE или LAST/PREVPRICE.
        change_pct: Optional[Decimal] = ready_pct
        if change_pct is None:
            if chg is not None and prev not in (None, Decimal("0")):
                change_pct = (chg / prev) * Decimal("100")
            elif last is not None and prev not in (None, Decimal("0")):
                change_pct = ((last - prev) / prev) * Decimal("100")

        turnover = _to_dec(m.get("VALTODAY")) or _to_dec(m.get("VOLTODAY")) or Decimal(0)
        volume = _to_dec(m.get("NUMTRADES")) or Decimal(0)

        rows.append(
            {
                "ticker": secid,
                "shortname": (s.get("SHORTNAME") or "").strip(),
                "lot_size": int(_to_dec(s.get("LOTSIZE")) or 1),
                "last": last,                              # Decimal | None
                "change_pct": change_pct,                  # Decimal | None
                "turnover": int(turnover),
                "volume": int(volume),
            }
        )

    return engine, market, rows


# ---------- command -------------------------------------------------------------

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
        d: dt.date
        if opt.get("date"):
            try:
                d = dt.datetime.strptime(opt["date"], "%Y-%m-%d").date()
            except ValueError:
                raise CommandError("date должен быть в формате YYYY-MM-DD")
        else:
            d = dt.date.today()

        self.stdout.write(f"→ Загружаю heatmap board={board}, date={d}, label={label}")

        engine, market, rows = fetch_board(board)
        if not rows:
            raise CommandError("MOEX вернул пустые данные")

        snap, _ = HeatSnapshot.objects.get_or_create(
            date=d, board=board, label=label, defaults={"source": "moex"}
        )
        # перезаписываем содержимое среза
        snap.tiles.all().delete()

        tiles: List[HeatTile] = []
        for r in rows:
            tiles.append(
                HeatTile(
                    snapshot=snap,
                    ticker=r["ticker"],
                    shortname=r["shortname"],
                    engine=engine,              # убери, если этих полей нет в модели
                    market=market,              # убери, если этих полей нет в модели
                    board=board,                # убери, если этих полей нет в модели
                    last=(r["last"] or Decimal("0")),
                    change_pct=r["change_pct"],  # допускаем None
                    turnover=r["turnover"],
                    volume=r["volume"],
                    lot_size=r["lot_size"],
                )
            )

        HeatTile.objects.bulk_create(tiles, batch_size=1000)
        self.stdout.write(self.style.SUCCESS(f"OK: {snap} — сохранено {len(tiles)} тикеров."))
