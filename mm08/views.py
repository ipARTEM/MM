# D:\MM\mm08\views.py
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_datetime
from django.http import JsonResponse
from django.db.models import F
from .models import Instrument, Candle
from .serializers import CandleSerializer

def home(request):
    return render(request, 'mm08/index.html', {'title': 'MM08 — старт'})


def chart(request, ticker: str):
    inst = get_object_or_404(Instrument, ticker=ticker.upper())
    # допустимые интервалы
    intervals = [1, 10, 60, 1440]
    try:
        interval = int(request.GET.get("interval", 60))
    except (TypeError, ValueError):
        interval = 60
    if interval not in intervals:
        interval = 60

    return render(
        request,
        "mm08/chart.html",
        {
            "instrument": inst,
            "interval": interval,
            "intervals": intervals,  # <-- передаём в шаблон
        },
    )

def chart_data(request, ticker: str):
    inst = get_object_or_404(Instrument, ticker=ticker.upper())
    interval = int(request.GET.get("interval", 60))
    qs = (Candle.objects
          .filter(instrument=inst, interval=interval)
          .order_by("dt")
          .values("dt", "open", "high", "low", "close", "volume")[:5000])
    data = [
        {
            "t": c["dt"].isoformat(),
            "o": c["open"],
            "h": c["high"],
            "l": c["low"],
            "c": c["close"],
            "v": c["volume"],
        }
        for c in qs
    ]
    return JsonResponse({"data": data})

def instrument_list(request):
    instruments = Instrument.objects.order_by("ticker")
    return render(request, "mm08/instruments.html", {"instruments": instruments})

def candle_list(request, ticker: str):
    inst = get_object_or_404(Instrument, ticker=ticker.upper())
    candles = inst.candles.order_by("-dt")[:300]  # последние 300
    return render(request, "mm08/candles.html", {"instrument": inst, "candles": candles})
