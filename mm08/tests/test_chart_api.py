# MM/mm08/tests/test_chart_api.py
from django.urls import reverse
from mm08.models import Candle

def test_chart_data_json(logged_client, mixer):
    inst = mixer.blend("mm08.Instrument", ticker="SBER")
    mixer.cycle(5).blend("mm08.Candle", instrument=inst, interval=Candle.Interval.H1)
    url = reverse("mm08:chart_data", kwargs={"ticker": "SBER"}) + "?interval=60"
    r = logged_client.get(url)
    assert r.status_code == 200
    payload = r.json()
    assert "data" in payload and len(payload["data"]) == 5
    assert {"t", "o", "h", "l", "c", "v"} <= set(payload["data"][0].keys())
