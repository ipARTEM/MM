# Project/mm08/services/iss_client.py
from __future__ import annotations
import json
import urllib.request
from typing import Dict, List, Tuple, Optional
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ISS_BASE = "https://iss.moex.com/iss"
DEFAULT_HEADERS = {
    "User-Agent": "MM-Training/1.0",
    "Accept": "application/json",
}
_session: Optional[requests.Session] = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        retry = Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=[502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        _session = s
    return _session

def _block(js: dict, name: str):
    cols = js[name]["columns"]
    rows = js[name]["data"]
    idx = {c: i for i, c in enumerate(cols)}
    return idx, rows

def fetch_tqbr_all() -> List[dict]:
    """Акции, доска TQBR (engine=stock, market=shares) — все страницы."""
    start, acc = 0, []
    while True:
        js = _get_json(
            "/engines/stock/markets/shares/boards/TQBR/securities.json",
            params={"iss.meta": "off", "iss.only": "securities,marketdata", "start": str(start)},
        )
        s_idx, s_rows = _block(js, "securities")
        m_idx, m_rows = _block(js, "marketdata")
        md = {r[m_idx.get("SECID")]: r for r in m_rows if r[m_idx.get("SECID")]}

        page = []
        for r in s_rows:
            secid = r[s_idx.get("SECID")]
            if not secid or secid not in md:
                continue
            m = md[secid]

            def g(row, idx, name, default=None):
                i = idx.get(name)
                return row[i] if i is not None else default

            last = g(m, m_idx, "LAST")
            ref = g(m, m_idx, "PREVPRICE") or g(m, m_idx, "OPEN")
            change_pct = None
            if last not in (None, 0) and ref not in (None, 0):
                change_pct = (last - ref) / ref * 100.0

            page.append({
                "SECID": secid,
                "SHORTNAME": g(r, s_idx, "SHORTNAME") or "",
                "BOARDID": g(r, s_idx, "BOARDID"),
                "LOTSIZE": g(r, s_idx, "LOTSIZE") or 1,
                "LAST": last,
                "OPEN": g(m, m_idx, "OPEN"),
                "HIGH": g(m, m_idx, "HIGH"),
                "LOW": g(m, m_idx, "LOW"),
                "PREVPRICE": g(m, m_idx, "PREVPRICE"),
                "VOLUME": g(m, m_idx, "VOLUME"),
                "VALTODAY": g(m, m_idx, "VALTODAY"),
                "CHANGE_PCT": change_pct,
            })
        if not page:
            break
        acc.extend(page)
        start += 100
    return acc


def _get_json(path: str, params: Optional[Dict[str, str]] = None,
              *, timeout: Tuple[float, float] = (3.0, 7.0)) -> dict:
    """path может быть /relative или полным https://..."""
    if path.startswith("http://") or path.startswith("https://"):
        url = path
    else:
        url = f"{ISS_BASE.rstrip('/')}/{path.lstrip('/')}"
    r = _get_session().get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _block_to_rows(js: dict, block: str) -> Tuple[List[str], List[List]]:
    cols = js[block]["columns"]
    rows = js[block]["data"]
    return cols, rows


def fetch_board_page(engine: str, market: str, board: str, *, start: int = 0) -> Tuple[List[dict], int]:
    """
    Возвращает кортеж: (строки-объединение securities+marketdata, total)
    """
    path = f"/engines/{engine}/markets/{market}/boards/{board}/securities.json"
    js = _get_json(
        path,
        {
            "iss.meta": "off",
            # cursor НУЖЕН, чтобы знать total и корректно пагинировать
            "iss.only": "securities,marketdata,securities.cursor",
            "start": str(start),
        },
    )

    securities = js.get("securities", {})
    marketdata = js.get("marketdata", {})
    cursor = js.get("securities.cursor", {})

    sec_cols = securities.get("columns", [])
    md_cols = marketdata.get("columns", [])
    sec_data = securities.get("data", []) or []
    md_data = marketdata.get("data", []) or []

    # total из курсора (если по какой-то причине нет — fallback на start+len)
    total = start + len(sec_data)
    cur_data = cursor.get("data", [])
    if cur_data:
        # у секций *.cursor в первом столбце TOTAL
        total = cur_data[0][0] if cur_data[0] and cur_data[0][0] is not None else total

    # индексы нужных колонок
    secid_i = sec_cols.index("SECID") if "SECID" in sec_cols else None
    short_i = sec_cols.index("SHORTNAME") if "SHORTNAME" in sec_cols else None
    board_i = sec_cols.index("BOARDID") if "BOARDID" in sec_cols else None

    md_by_secid: Dict[str, list] = {}
    if md_data and "SECID" in md_cols:
        md_secid_i = md_cols.index("SECID")
        for row in md_data:
            if row and md_secid_i < len(row):
                md_by_secid[row[md_secid_i]] = row

    last_i = md_cols.index("LAST") if "LAST" in md_cols else None
    chg_i = md_cols.index("LASTTOPREVPRICE") if "LASTTOPREVPRICE" in md_cols else None

    page: List[dict] = []
    for row in sec_data:
        secid = row[secid_i] if secid_i is not None else None
        mdr = md_by_secid.get(secid)
        last = mdr[last_i] if (mdr and last_i is not None and last_i < len(mdr)) else None
        change_pct = mdr[chg_i] if (mdr and chg_i is not None and chg_i < len(mdr)) else None

        page.append({
            "secid": secid,
            "shortname": row[short_i] if short_i is not None else None,
            "board": row[board_i] if board_i is not None else board,
            "last": last,
            "change_pct": change_pct,
        })

    return page, int(total)


def fetch_board_all(engine: str, market: str, board: str, *, max_pages: Optional[int] = None) -> List[dict]:
    start = 0
    out: List[dict] = []
    pages = 0
    total = None

    while True:
        page, total = fetch_board_page(engine, market, board, start=start)
        if not page:
            break
        out.extend(page)
        start += len(page)
        pages += 1

        # защита от бесконечного цикла
        if max_pages and pages >= max_pages:
            break
        if total is not None and start >= total:
            break

    return out


def fetch_tqbr_all(max_pages: Optional[int] = None) -> List[dict]:
    return fetch_board_all("stock", "shares", "TQBR", max_pages=max_pages)
