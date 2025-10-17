# MM/mm08/tests/test_models.py
import pytest
from django.db import IntegrityError
from mm08.models import Instrument, Candle

def test_instrument_save_normalizes(mixer):
    inst = mixer.blend(Instrument,
                       ticker=" sBeR ",
                       secid=" sber ",
                       board=" tqbr ",
                       engine=" STOCK ",
                       market=" SHARES ")
    inst.refresh_from_db()
    assert inst.ticker == "SBER"
    assert inst.secid == "SBER"
    assert inst.board == "TQBR"
    assert inst.engine == "stock"
    assert inst.market == "shares"

def test_candle_unique_constraint(mixer):
    inst = mixer.blend(Instrument, ticker="GAZP")
    c1 = mixer.blend(Candle, instrument=inst, interval=Candle.Interval.H1, volume=10)
    # та же тройка (instrument, dt, interval) должна давать ошибку
    with pytest.raises(IntegrityError):
        mixer.blend(Candle, instrument=inst, dt=c1.dt, interval=c1.interval)

def test_candle_bulk_create_fast(mixer):
    inst = mixer.blend(Instrument, ticker="GMKN")
    # создадим 100 свечей за один вызов
    candles = mixer.cycle(100).blend(
        Candle, instrument=inst, interval=Candle.Interval.M1
    )
    assert len(candles) == 100
