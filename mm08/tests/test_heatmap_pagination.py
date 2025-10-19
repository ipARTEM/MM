import pytest
from django.urls import reverse
from mm08.models import HeatSnapshot, HeatTile

@pytest.mark.django_db
def test_heatmap_pagination_basic(client, django_user_model):
    # подготовим снимок и 37 плиток
    snap = HeatSnapshot.objects.create(date="2025-10-18", board="TQBR", label="fast")
    tiles = [
        HeatTile(snapshot=snap, ticker=f"T{i}", shortname=f"Name{i}",
                 change_pct=i, last=100+i, turnover=0, volume=0, lot_size=1)
        for i in range(37)
    ]
    HeatTile.objects.bulk_create(tiles)

    url = reverse("mm08:heatmap") + "?board=TQBR&per=10&page=1"
    r = client.get(url)
    assert r.status_code == 200
    # на странице должно быть 10 карточек
    assert r.content.decode("utf-8").count('class="heat-tile"') == 10

    # последняя страница — 4-я (37 => 4 страницы по 10)
    url_last = reverse("mm08:heatmap") + "?board=TQBR&per=10&page=4"
    r2 = client.get(url_last)
    assert r2.status_code == 200
    assert r2.content.decode("utf-8").count('class="heat-tile"') == 7

@pytest.mark.django_db
def test_heatmap_per_fallback(client):
    snap = HeatSnapshot.objects.create(date="2025-10-18", board="TQBR", label="")
    HeatTile.objects.bulk_create([
        HeatTile(snapshot=snap, ticker=f"X{i}", shortname="",
                 change_pct=0, last=0, turnover=0, volume=0, lot_size=1)
        for i in range(12)
    ])
    # невалидное per -> падение к 20
    r = client.get(reverse("mm08:heatmap") + "?board=TQBR&per=999&page=1")
    assert r.status_code == 200
    # все 12 поместятся на одной странице
    assert r.content.decode("utf-8").count('class="heat-tile"') == 12
