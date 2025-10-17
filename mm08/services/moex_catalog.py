# D:\MM\mm08\services\moex_catalog.py
import logging
from typing import Dict, List, Tuple, Optional
from django.core.cache import cache
from requests import RequestException

from .moex_iss import MoexISSClient, InstrumentRowMapper
from .moex_meta import is_valid_combo

logger = logging.getLogger(__name__)

CATALOG_CACHE_KEY = "moex_catalog_{engine}_{market}_{board}"
CATALOG_TTL_SEC = 600  # 10 минут

def get_moex_list(engine: str, market: str, board: str) -> List[Tuple[str, str]]:
    """Закрытый список [(SECID, label)] для выпадашки. С кэшем и валидацией тройки."""
    if not is_valid_combo(engine, market, board):
        # неверная комбинация — ничего не трогаем
        logger.warning("Invalid combo for list: %s/%s/%s", engine, market, board)
        return []

    cache_key = CATALOG_CACHE_KEY.format(engine=engine, market=market, board=board)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    client = MoexISSClient(timeout=10, pause_sec=0.0)
    options: List[Tuple[str, str]] = []

    try:
        for rec in client.iter_securities(engine=engine, market=market, board=board):
            secid = (rec.get("SECID") or rec.get("secid") or "").strip().upper()
            if not secid:
                continue
            shortname = (rec.get("SHORTNAME") or rec.get("shortname") or "").strip()
            label = f"{secid} — {shortname}" if shortname else secid
            options.append((secid, label))
    except RequestException as e:
        logger.exception("ISS request failed for %s/%s/%s: %s", engine, market, board, e)
        return []

    options.sort(key=lambda x: x[0])
    cache.set(cache_key, options, timeout=CATALOG_TTL_SEC)
    return options


def get_moex_info(engine: str, market: str, board: str, secid: str) -> Optional[Dict]:
    """Подробности по одному SECID для автозаполнения."""
    if not is_valid_combo(engine, market, board):
        logger.warning("Invalid combo for info: %s/%s/%s", engine, market, board)
        return None

    client = MoexISSClient(timeout=10, pause_sec=0.0)
    wanted = (secid or "").strip().upper()
    if not wanted:
        return None

    try:
        for rec in client.iter_securities(engine=engine, market=market, board=board):
            rec_secid = (rec.get("SECID") or rec.get("secid") or "").strip().upper()
            if rec_secid == wanted:
                return InstrumentRowMapper.to_instrument_defaults(rec) | {"ticker": wanted}
    except RequestException as e:
        logger.exception("ISS request failed for %s/%s/%s %s: %s", engine, market, board, wanted, e)
        return None

    return None
