# Project/mm08/services/heatmap.py
from __future__ import annotations

import datetime as dt
from typing import Dict, List, Tuple, Optional

import requests
from django.db import transaction

from mm08.models import Instrument, HeatSnapshot, HeatTile
from django.utils import timezone


# --- Константы и утилиты -----------------------------------------------------

# Сопоставление борд -> (engine, market)
BOARD_MAP: Dict[str, Tuple[str, str]] = {
    "TQBR": ("stock", "shares"),   # акции
    "RFUD": ("futures", "forts"),  # фьючерсы
    # при необходимости добавляйте другие доски
}

ISS_BASE = "https://iss.moex.com/iss"


def _iss_board_url(board: str) -> str:
    engine, market = BOARD_MAP[board]
    # В marketdata есть LAST, LASTTOPREVPRICE, CHANGE и т.д.
    return (
        f"{ISS_BASE}/engines/{engine}/markets/{market}/boards/{board}/"
        f"securities.json?iss.meta=off&iss.only=securities,marketdata"
    )


def _fetch_board_data(board: str) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """
    Тянем секции `securities` и `marketdata` и раскладываем их в словари по SECID.
    Возвращаем (securities_by_secid, marketdata_by_secid)
    """
    url = _iss_board_url(board)
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    # Парсим securities
    sec_cols = data["securities"]["columns"]
    sec_pos = {c: i for i, c in enumerate(sec_cols)}
    securities = {}
    for row in data["securities"]["data"]:
        secid = row[sec_pos.get("SECID")]
        if not secid:
            continue
        securities[secid] = {
            "secid": secid,
            "shortname": row[sec_pos.get("SHORTNAME")],
            "board": row[sec_pos.get("BOARDID")] or board,
        }

    # Парсим marketdata
    md_cols = data["marketdata"]["columns"]
    md_pos = {c: i for i, c in enumerate(md_cols)}
    marketdata = {}
    for row in data["marketdata"]["data"]:
        secid = row[md_pos.get("SECID")]
        if not secid:
            continue
        last = row[md_pos.get("LAST")]
        # LASTTOPREVPRICE у акций — это отношение LAST к PREVPRICE в %
        # Преобразуем к "изменение, %" (т.е. -1.25, +2.10 и т.д.)
        last_to_prev_pct = row[md_pos.get("LASTTOPREVPRICE")]
        change_pct = None
        if last_to_prev_pct is not None:
            try:
                change_pct = float(last_to_prev_pct) - 100.0
            except Exception:
                change_pct = None

        marketdata[secid] = {
            "last": last,
            "change_pct": change_pct,
        }

    return securities, marketdata


# --- Публичный API ------------------------------------------------------------

def build_snapshot(
    board: str,
    label: str = "fast",
    date: Optional[str] = None,
    replace: bool = True,
) -> Tuple[HeatSnapshot, bool]:
    """
    Собирает снимок теплокарты: тянет котировки ISS, апсертит инструменты и плитки.

    Parameters
    ----------
    board : str
        Код доски (например, 'TQBR', 'RFUD').
    label : str, optional
        Метка снимка ('fast' / 'fresh' и т.п.), по умолчанию 'fast'.
    date : Optional[str], optional
        Явная дата снимка в формате YYYY-MM-DD; по умолчанию сегодня.
    replace : bool, optional
        Если True и снимок существует — перезаполняем плитки. По умолчанию True.

    Returns
    -------
    (snapshot, created) : Tuple[HeatSnapshot, bool]
    """
    board = (board or "TQBR").upper()
    if board not in BOARD_MAP:
        raise ValueError(f"Unsupported board: {board}")

    # Дата снимка
    if date:
        snap_date = dt.date.fromisoformat(date)
    else:
        snap_date = dt.date.today()

    # Тянем данные с ISS
    securities, marketdata = _fetch_board_data(board)

    with transaction.atomic():
        # Снапшот
        snapshot, created = HeatSnapshot.objects.get_or_create(
            board=board,
            label=label or "",
            date=snap_date,
            # defaults={"created_at": dt.datetime.now()},    # ← можно, если у модели нет auto_now_add
        )

        if not created and replace:
            HeatTile.objects.filter(snapshot=snapshot).delete()

        # Апсерты инструментов и создание плиток
        tiles: List[HeatTile] = []
        for secid, sec in securities.items():
            md = marketdata.get(secid, {})
            last = md.get("last")
            change_pct = md.get("change_pct")

            inst, _ = Instrument.objects.update_or_create(
                board=board,
                ticker=secid,
                defaults={
                    "shortname": sec.get("shortname") or secid,
                    "engine": BOARD_MAP[board][0],
                },
            )

            # безопасное значение для last: модель NOT NULL → подставим 0, если None
            last_safe = last if last is not None else 0

            tiles.append(
                HeatTile(
                    snapshot=snapshot,
                    ticker=inst.ticker,
                    shortname=inst.shortname,
                    last=last_safe,             # ← используем безопасное значение
                    change_pct=change_pct,      # может быть None — модель это допускает
                )
            )


        if tiles:
            HeatTile.objects.bulk_create(tiles, batch_size=500)

    return snapshot, created





