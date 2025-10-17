import pytest
from django.urls import reverse
from django.utils import timezone
from mm08.models import Instrument, Candle

@pytest.mark.django_db
def test_home_page_accessible(client):
    """Главная доступна всем (200)."""
    resp = client.get(reverse("mm08:home"))
    assert resp.status_code == 200
    assert b"MM08" in resp.content  # есть заголовок

@pytest.mark.django_db
def test_instrument_list_requires_login(client, auth_client_analyst):
    """Список инструментов требует логин."""
    url = reverse("mm08:instrument_list")

    # Аноним — редирект на логин (302)
    r1 = client.get(url)
    assert r1.status_code in (302, 301)
    assert "login" in r1["Location"]

    # Авторизованный аналитик — 200
    r2 = auth_client_analyst.get(url)
    assert r2.status_code == 200

@pytest.mark.django_db
def test_candle_list_redirects_if_ticker_not_found(auth_client_analyst):
    """Неизвестный тикер -> редирект на список с message."""
    url = reverse("mm08:candle_list", args=["NOPE"])
    r = auth_client_analyst.get(url, follow=False)
    assert r.status_code in (302, 301)
    assert reverse("mm08:instrument_list") in r["Location"]

@pytest.mark.django_db
def test_chart_and_chart_data(auth_client_analyst):
    """Страница графика и JSON-данные для реально существующего инструмента."""
    inst = Instrument.objects.create(ticker="SBER")
    # пару свечей для JSON
    now = timezone.now()
    Candle.objects.create(instrument=inst, dt=now, interval=60, open=10, high=11, low=9, close=10, volume=100)
    Candle.objects.create(instrument=inst, dt=now + timezone.timedelta(minutes=60), interval=60,
                          open=10, high=12, low=9, close=11, volume=120)

    # страница графика
    page = auth_client_analyst.get(reverse("mm08:chart", args=[inst.ticker]) + "?interval=60")
    assert page.status_code == 200
    assert b"График" in page.content

    # JSON для графика
    data = auth_client_analyst.get(reverse("mm08:chart_data", args=[inst.ticker]) + "?interval=60")
    assert data.status_code == 200
    payload = data.json()
    assert "data" in payload and len(payload["data"]) >= 2
    one = payload["data"][0]
    # проверим ключи одной свечи
    for k in ("t", "o", "h", "l", "c", "v"):
        assert k in one

@pytest.mark.django_db
def test_dashboard_shows_rows(auth_client_analyst):
    """Дашборд: считает активные и выводит строки."""
    inst = Instrument.objects.create(ticker="GAZP", shortname="GAZP")
    auth_client_analyst.get(reverse("mm08:dashboard"))  # просто чтобы создать шаблон-кэш, если есть
    resp = auth_client_analyst.get(reverse("mm08:dashboard"))
    assert resp.status_code == 200
    assert b"Дашборд" in resp.content
    # хотя бы тикер в HTML
    assert b"GAZP" in resp.content

@pytest.mark.django_db
def test_permissions_instrument_create_forbidden_for_analyst(auth_client_analyst):
    """Аналитик не может открыть /instruments/new/ — получит дружелюбный 403."""
    url = reverse("mm08:instrument_create")
    r = auth_client_analyst.get(url)
    assert r.status_code == 403
    assert b"Доступ запрещ" in r.content  # кусочек заголовка из 403.html

@pytest.mark.django_db
def test_permissions_instrument_create_ok_for_manager(auth_client_manager):
    """Менеджер открывает форму и может создать инструмент."""
    url = reverse("mm08:instrument_create")

    # GET — форма доступна
    r1 = auth_client_manager.get(url)
    assert r1.status_code == 200
    assert b"Добавить инструмент" in r1.content

    # POST — создаём
    form = {
        "ticker": "GMKN",
        "secid": "",
        "shortname": "GMKN",
        "engine": "stock",
        "market": "shares",
        "board": "TQBR",
        "lot_size": 1,
        "is_active": True,
    }
    r2 = auth_client_manager.post(url, form, follow=False)
    # после успешного сохранения — редирект на список
    assert r2.status_code in (302, 301)
    assert reverse("mm08:instrument_list") in r2["Location"]
