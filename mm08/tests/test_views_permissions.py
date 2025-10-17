from django.urls import reverse
from ._utils import html
from mm08.models import Instrument

def test_create_requires_permission(client, analyst):
    client.login(username="analyst", password="p")
    r = client.get(reverse("mm08:instrument_create"))
    # 403 уже есть — этого достаточно. Дополнительно проверим, что страница дружелюбная.
    assert r.status_code == 403
    page = html(r)
    # Не привязываемся к одной фразе — ловим общий заголовок страницы.
    assert ("Доступ запрещ" in page) or ("🚫" in page)



