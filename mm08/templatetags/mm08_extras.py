from django import template

register = template.Library()

@register.simple_tag
def page_window(page_obj, window=5):
    """
    Возвращает список номеров страниц длиной ≤ window (по умолчанию 5),
    центрируя текущее значение где возможно.
    """
    total = page_obj.paginator.num_pages
    current = page_obj.number
    if total <= window:
        return list(range(1, total + 1))

    half = window // 2  # 2 при window=5
    start = max(1, current - half)
    end = start + window - 1
    if end > total:
        end = total
        start = max(1, end - window + 1)
    return list(range(start, end + 1))
