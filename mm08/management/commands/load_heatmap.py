# mm08/management/commands/load_heatmap.py
from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Tuple, List, Dict, Any

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
    b = (board or "").upper().strip()

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

def _to_decimal(x: Any) -> Decimal | None:
    if x in (None, "", "-", "NaN", "nan"):
        return None
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def _rows_from_table(tbl: Any) -> List[Dict[str, Any]]:
    """
    Унифицируем таблицу ISS в список словарей.
    Поддерживает:
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
    out: List[Dict[str, Any]] = []
    for row in data:
        out.append({cols[i]: row[i] for i in range(min(len(cols), len(row)))})
    return out


def fetch_board(board: str) -> tuple[str, str, list[dict]]:
    """
    Возвращает (engine, market, rows) для выбранного board.
    rows = [{ticker, shortname, lot_size, last, change_pct, turnover, volume}, ...]
    """
    engine, market, URL = resolve_path(board)

    # NB: добавили LASTTOPREVPRICE — это надёжный источник процента.
    SEC_COLS = "SECID,SHORTNAME,LOTSIZE"
    MD_COLS = (
        "SECID,LAST,OPEN,PREVPRICE,CHANGE,LASTCHANGEPRC,LASTTOPREVPRICE,VALTODAY,VOLTODAY,NUMTRADES"
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

    md_by_secid = {row.get("SECID"): row for row in md_rows if isinstance(row, dict) and row.get("SECID")}

    rows: list[dict] = []
    for s in sec_rows:
        secid = s.get("SECID")
        if not secid:
            continue
        m = md_by_secid.get(secid) or {}

        last = _to_decimal(m.get("LAST"))
        prev = _to_decimal(m.get("PREVPRICE"))
        chg = _to_decimal(m.get("CHANGE"))
        ready_pct = _to_decimal(m.get("LASTCHANGEPRC"))
        ltp = _to_decimal(m.get("LASTTOPREVPRICE"))  # отношение last/prev

        # Правильный %: сначала готовый, затем из LASTTOPREVPRICE, затем из CHANGE/PREVPRICE, затем LAST/PREVPRICE
        change_pct = ready_pct
        if change_pct is None and ltp not in (None, Decimal("0")):
            change_pct = (ltp - Decimal("1")) * Decimal("100")
        if change_pct is None and chg is not None and prev not in (None, Decimal("0")):
            change_pct = (chg / prev) * Decimal("100")
        if change_pct is None and last is not None and prev not in (None, Decimal("0")):
            change_pct = ((last - prev) / prev) * Decimal("100")

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
    help = "Загрузить теплокарту MOEX. Пример: --board TQBR --label fast"

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, help="YYYY-MM-DD")
        parser.add_argument("--board", type=str, default="TQBR")
        parser.add_argument("--label", type=str, default="fast")

    @transaction.atomic
    def handle(self, *args, **opt):
        board = (opt.get("board") or "TQBR").upper()
        label = (opt.get("label") or "fast").strip()
        d = dt.datetime.strptime(opt["date"], "%Y-%m-%d").date() if opt.get("date") else dt.date.today()

        engine, market, rows = fetch_board(board)
        if not rows:
            raise CommandError("ISS вернул пустые данные.")

        snap, _ = HeatSnapshot.objects.get_or_create(
            date=d, board=board, label=label, defaults={"source": "moex"}
        )
        snap.created_at = dt.datetime.now()
        snap.source = "moex"
        snap.save(update_fields=["created_at", "source"])

        snap.tiles.all().delete()
        HeatTile.objects.bulk_create(
            [
                HeatTile(
                    snapshot=snap,
                    ticker=r["ticker"],
                    shortname=r.get("shortname") or "",
                    engine=engine, market=market, board=board,
                    last=r.get("last") or 0,
                    change_pct=r.get("change_pct"),
                    turnover=r.get("turnover") or 0,
                    volume=r.get("volume") or 0,
                    lot_size=r.get("lot_size") or 1,
                )
                for r in rows
            ],
            batch_size=1000,
        )

        self.stdout.write(self.style.SUCCESS(f"OK: {snap} — сохранено {len(rows)} тикеров."))
