# Project/mm08/services/pagination.py

from typing import List  # импортируем типы для подсказок

def window_numbers(page, radius: int = 5) -> List[int]:
    # type: (object, int) -> List[int]
    # Функция возвращает список номеров страниц вокруг текущей — для удобной навигации в пагинации.
    # page: объект django.core.paginator.Page
    # radius: сколько номеров показывать слева/справа от текущей страницы

    try:
        current: int = int(page.number)                  # получаем номер текущей страницы
        last: int = int(page.paginator.num_pages)        # количество всех страниц
    except Exception:
        return []                                        # если что-то не так — возвращаем пустой список

    start: int = max(1, current - radius)               # левая граница окна
    end: int = min(last, current + radius)              # правая граница окна

    return list(range(start, end + 1))                  # формируем список номеров [start, ..., end]
