import pytest
from datetime import datetime, timedelta, timezone as dt_tz
from django.db import IntegrityError
from mm08.models import Instrument, Candle

@pytest.mark.django_db
def test_instrument_normalization_and_str():
    """Сохраняем «грязные» значения и проверяем нормализацию + __str__."""
    inst = Instrument.objects.create(
        ticker="  sBeR ",
        secid=" sBer  ",
        shortname="Сбербанк",
        engine=" STOCK ",
        market=" Shares ",
        board=" tqbr ",
        lot_size=10,
    )
    # тикер/SECID/board → UPPER, engine/market → lower
    assert inst.ticker == "SBER"
    assert inst.secid == "SBER"
    assert inst.board == "TQBR"
    assert inst.engine == "stock"
    assert inst.market == "shares"
    assert str(inst) == "SBER"
    # базовые даты проставились
    assert inst.created_at is not None
    assert inst.updated_at is not None

@pytest.mark.django_db
def test_candle_unique_and_ordering():
    """unique_together(instrument, dt, interval) и сортировка по -dt."""
    inst = Instrument.objects.create(ticker="GAZP")
    t1 = datetime(2025, 1, 1, 10, tzinfo=dt_tz.utc)
    t2 = t1 + timedelta(hours=1)

    c1 = Candle.objects.create(instrument=inst, dt=t1, interval=Candle.Interval.H1, open=1, high=2, low=1, close=2)
    c2 = Candle.objects.create(instrument=inst, dt=t2, interval=Candle.Interval.H1, open=2, high=3, low=2, close=3)

    # уникальность по (instrument, dt, interval)
    with pytest.raises(IntegrityError):
        Candle.objects.create(instrument=inst, dt=t1, interval=Candle.Interval.H1, open=0, high=0, low=0, close=0)

    # ordering = ['-dt'] — первой должна быть свежая свеча
    qs = list(Candle.objects.filter(instrument=inst))
    assert qs[0].dt == t2
    assert qs[1].dt == t1
