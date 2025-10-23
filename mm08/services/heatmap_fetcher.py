# mm08/services/heatmap_fetch.py
from __future__ import annotations
import requests
from decimal import Decimal, InvalidOperation

def _to_decimal(x):
    if x in (None, "", "-"):
        return None
    try:
        return Decimal(str(x))
    except InvalidOperation:
        return None

def _rows_from_table(tbl) -> list[dict]:
    if not tbl:
        return []
    if isinstance(tbl, list):
        if tbl and isinstance(tbl[0], dict):
            return tbl
        return []
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

def _resolve_path(board: str) -> tuple[str, str, str]:
    b = (board or "").upper()
    if b.startswith("RF"):  # FORTS
        return (
            "futures",
            "forts",
            "https://iss.moex.com/iss/engines/futures/markets/forts/boards/{board}/securities.json",
        )
    return (
        "stock",
        "shares",
        "https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities.json",
    )

def fetch_board(board: str) -> tuple[str, str, list[dict]]:
    """
    Возвращает (engine, market, rows) для выбранного борда.
    rows: [{ticker, shortname, lot_size, last, change_pct, turnover, volume}, ...]
    """
    engine, market, URL = _resolve_path(board)

    SEC_COLS = "SECID,SHORTNAME,LOTSIZE"
    MD_COLS = "SECID,LAST,PREVPRICE,CHANGE,LASTCHANGEPRC,VALTODAY,VOLTODAY,NUMTRADES"

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

    sec_tbl = raw.get("securities") if isinstance(raw, dict) else None
    md_tbl = raw.get("marketdata") if isinstance(raw, dict) else None
    if sec_tbl is None or md_tbl is None and isinstance(raw, list):
        for part in raw:
            if isinstance(part, dict):
                sec_tbl = sec_tbl or part.get("securities")
                md_tbl = md_tbl or part.get("marketdata")

    sec_rows = _rows_from_table(sec_tbl)
    md_rows = _rows_from_table(md_tbl)
    md_by = {row.get("SECID"): row for row in md_rows if isinstance(row, dict)}

    rows = []
    for s in sec_rows:
        secid = s.get("SECID")
        if not secid:
            continue
        m = md_by.get(secid) or {}

        last = _to_decimal(m.get("LAST"))
        prev = _to_decimal(m.get("PREVPRICE"))
        chg = _to_decimal(m.get("CHANGE"))
        ready_pct = _to_decimal(m.get("LASTCHANGEPRC"))

        change_pct = ready_pct
        if change_pct is None:
            if chg is not None and prev not in (None, Decimal("0")):
                change_pct = (chg / prev) * Decimal("100")
            elif last is not None and prev not in (None, Decimal("0")):
                change_pct = ((last - prev) / prev) * Decimal("100")

        turnover = m.get("VALTODAY") or m.get("VOLTODAY") or 0
        volume = m.get("NUMTRADES") or 0

        rows.append({
            "ticker": secid,
            "shortname": s.get("SHORTNAME") or "",
            "lot_size": int(s.get("LOTSIZE") or 1),
            "last": float(last) if last is not None else 0.0,
            "change_pct": float(change_pct) if change_pct is not None else None,
            "turnover": int(turnover or 0),
            "volume": int(volume or 0),
        })

    return engine, market, rows
