# Project/mm08/services/pagination.py
from __future__ import annotations
from typing import List

def window_numbers(current: int, total: int, window_size: int = 5) -> List[int]:
    """Возвращает окно номеров страниц вокруг текущей.

    Parameters
    ----------
    current : int
        Текущий номер страницы (1-based).
    total : int
        Общее число страниц.
    window_size : int, optional
        Ширина окна, по умолчанию 5.

    Returns
    -------
    List[int]
        Список номеров страниц для пагинации.
    """
    if total <= 0:
        return []
    current = max(1, min(current, total))
    window_size = max(1, window_size)

    half = window_size // 2
    start = max(1, current - half)
    end = min(total, start + window_size - 1)
    start = max(1, end - window_size + 1)
    return list(range(start, end + 1))
