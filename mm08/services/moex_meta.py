# MM\mm08\services\moex_meta.py
# --- Каноничный закрытый список допустимых комбинаций для UI ---

from typing import Dict, List, Tuple

# NB: этого достаточно для нашего UI. При желании можно расширить.
ENGINE_META = {
    "stock": {  # фондовый рынок
        "default_market": "shares",
        "default_board": "TQBR",
        "markets": {
            "shares": ["TQBR"],  # акции
        },
    },
    "futures": {  # срочный рынок (FORTS)
        "default_market": "forts",
        "default_board": "RFUD",
        "markets": {
            "forts": ["RFUD"],  # дневная основная сессия FORTS
        },
    },
    "currency": {  # валютный рынок
        "default_market": "spot",
        "default_board": "CETS",
        "markets": {
            "spot": ["CETS"],
        },
    },
}

def get_engines() -> List[Tuple[str, str]]:
    return [(k, k) for k in ENGINE_META.keys()]

def get_markets(engine: str) -> List[Tuple[str, str]]:
    meta = ENGINE_META.get(engine, {})
    return [(m, m) for m in meta.get("markets", {}).keys()]

def get_boards(engine: str, market: str) -> List[Tuple[str, str]]:
    meta = ENGINE_META.get(engine, {})
    boards = meta.get("markets", {}).get(market, [])
    return [(b, b) for b in boards]

def get_defaults(engine: str) -> Tuple[str, str]:
    meta = ENGINE_META.get(engine, {})
    return meta.get("default_market", ""), meta.get("default_board", "")

def is_valid_combo(engine: str, market: str, board: str) -> bool:
    return board in [b for (b, _) in get_boards(engine, market)]
