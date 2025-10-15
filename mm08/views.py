# D:\MM\mm08\views.py
from rest_framework.response import Response
from rest_framework.decorators import api_view
from django.contrib import messages
from django.shortcuts import get_object_or_404, render, redirect
from django.utils.dateparse import parse_datetime
from django.urls import reverse
from django.http import JsonResponse
from django.db.models import F, Max
from .models import Instrument, Candle
from .serializers import CandleSerializer
from .forms import InstrumentForm, CandleFilterForm

def home(request):
    return render(request, 'mm08/index.html', {'title': 'MM08 — старт'})


def chart(request, ticker: str):
    t = (ticker or "").strip()
    instrument = Instrument.objects.filter(ticker__iexact=t).first()
    if not instrument:
        messages.error(request, f"Инструмент «{ticker}» не найден.")
        return redirect("mm08:instrument_list")

    interval = request.GET.get("interval", "60")
    return render(request, "mm08/chart.html", {
        "title": f"График {instrument.ticker}",
        "instrument": instrument,
        "interval": interval,
    })

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
    t = (ticker or "").strip()
    instrument = Instrument.objects.filter(ticker__iexact=t).first()
    if not instrument:
        messages.error(request, f"Инструмент «{ticker}» не найден.")
        return redirect("mm08:instrument_list")

    interval = request.GET.get("interval")  # если передаётся — можешь использовать в фильтре
    qs = Candle.objects.filter(instrument=instrument)
    if interval:
        qs = qs.filter(interval=interval)
    candles = qs.order_by("-dt")[:500]

    return render(request, "mm08/candles.html", {
        "title": f"Свечи {instrument.ticker}",
        "instrument": instrument,
        "candles": candles,
    })


def instrument_create(request):
    """Страница с ModelForm для добавления нового инструмента."""
    if request.method == "POST":
        form = InstrumentForm(request.POST)
        if form.is_valid():                     # валидация полей формы
            form.save()                         # сохраняем в БД
            return redirect("mm08:instrument_list")
    else:
        form = InstrumentForm()                 # пустая форма для GET

    return render(request, "mm08/instrument_form.html", {
        "title": "Добавить инструмент",
        "form": form,
    })

def candle_filter(request):
    """Страница с формой выбора тикера/интервала. Редирект на /candles/<ticker>/?interval=..."""
    form = CandleFilterForm(request.GET or None)
    if form.is_valid():
        inst = form.cleaned_data["instrument"]  # выбранный инструмент
        interval = form.cleaned_data["interval"]
        url = reverse("mm08:candle_list", args=[inst.ticker])
        return redirect(f"{url}?interval={interval}")

    return render(request, "mm08/candle_filter.html", {
        "title": "Фильтр свечей",
        "form": form,
    })

def dashboard(request):
    """Простая сводка: количество активных инструментов, дата последней свечи по каждому."""
    instruments = Instrument.objects.filter(is_active=True).order_by("ticker")
    # Собираем последнюю дату свечи по каждому инструменту (по всем интервалам сразу)
    last_dt_map = (
        Candle.objects
        .values("instrument__ticker")
        .annotate(last_dt=Max("dt"))
        .order_by()
    )
    # Превращаем в словарь { 'TICKER': datetime }
    last_dt_dict = {row["instrument__ticker"]: row["last_dt"] for row in last_dt_map}

    rows = []
    for inst in instruments:
        rows.append({
            "ticker": inst.ticker,
            "shortname": inst.shortname,
            "market": inst.market,
            "last_dt": last_dt_dict.get(inst.ticker),
        })

    return render(request, "mm08/dashboard.html", {
        "title": "Дашборд",
        "total_active": instruments.count(),
        "rows": rows,
    })
