import time
import logging
from typing import Dict, Optional, Iterable
import requests

logger = logging.getLogger(__name__)


class MoexISSClient:
    """Клиент ISS с «правильным» адресом под конкретный engine/market/board."""

    BASE = "https://iss.moex.com/iss"

    def __init__(self, timeout: int = 20, pause_sec: float = 0.2):
        self.timeout = timeout                    # таймаут HTTP
        self.pause_sec = pause_sec                # пауза между страницами (бережём API)
        self.session = requests.Session()         # сессия → быстрее повторные запросы

    def _get(self, path: str, params: Optional[Dict] = None) -> Dict:
        """GET → JSON с проверкой статуса."""
        url = f"{self.BASE}/{path}"
        r = self.session.get(url, params=params or {}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _build_path(self, engine: Optional[str], market: Optional[str], board: Optional[str]) -> str:
        """
        Если заданы engine/market/board — используем узкоспециализированный путь:
          /iss/engines/{engine}/markets/{market}/boards/{board}/securities.json
        Иначе — общий /iss/securities.json (но лучше всегда задавать фильтры).
        """
        if engine and market and board:
            return f"engines/{engine}/markets/{market}/boards/{board}/securities.json"
        return "securities.json"

    def iter_securities(self, engine: Optional[str], market: Optional[str], board: Optional[str]) -> Iterable[Dict]:
        """
        Постраничный итератор по таблице 'securities' (узел с колонками/данными).
        """
        start = 0
        page = 100
        path = self._build_path(engine, market, board)

        while True:
            data = self._get(path, params={"start": start})
            sec = data.get("securities", {})
            cols = sec.get("columns", [])
            rows = sec.get("data", [])

            if not rows:
                break

            for row in rows:
                # превращаем массив значений в dict по именам колонок
                yield dict(zip(cols, row))

            if len(rows) < page:
                break

            start += page
            time.sleep(self.pause_sec)


class InstrumentRowMapper:
    """Маппинг ответа ISS → поля твоей модели Instrument с защитой от сюрпризов."""

    @staticmethod
    def _get(rec: Dict, *keys: str, default: str = "") -> str:
        """
        Безопасно достаём значение по одному из ключей (SECID/secid/…),
        приводим к строке и обрезаем пробелы.
        """
        for k in keys:
            if k in rec and rec[k] is not None:
                return str(rec[k]).strip()
        return default

    @staticmethod
    def to_instrument_defaults(rec: Dict) -> Dict:
        """Возвращаем defaults для update_or_create под твою модель."""
        secid = InstrumentRowMapper._get(rec, "SECID", "secid").upper()
        shortname = InstrumentRowMapper._get(rec, "SHORTNAME", "shortname")
        engine = InstrumentRowMapper._get(rec, "ENGINE", "engine", default="stock").lower()
        market = InstrumentRowMapper._get(rec, "MARKET", "market", default="shares").lower()
        board  = InstrumentRowMapper._get(rec, "BOARDID", "boardid", default="TQBR").upper()

        lot_raw = InstrumentRowMapper._get(rec, "LOTSIZE", "BOARDLOT", "LOTS", default="1")
        try:
            lot_size = int(lot_raw)
        except ValueError:
            lot_size = 1

        return {
            "secid": secid,
            "shortname": shortname,
            "engine": engine,
            "market": market,
            "board": board,
            "lot_size": lot_size,
            "is_active": True,
        }
