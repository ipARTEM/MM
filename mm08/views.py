from django.contrib import messages
from django.http import JsonResponse, HttpResponseRedirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import TemplateView, ListView, CreateView, FormView, DetailView
from django.shortcuts import redirect
from django.db.models import Max

from .models import Instrument, Candle
from .forms import InstrumentForm, CandleFilterForm


# ---------- MIXINS ----------
class InstrumentByTickerMixin:
    """Достаёт инструмент по <ticker> из URL (без учёта регистра).
    Если не найден — показывает message и уводит на список."""
    instrument_context_name = "instrument"

    def get_ticker(self):
        return (self.kwargs.get("ticker") or "").strip()

    def get_instrument(self):
        t = self.get_ticker()
        return Instrument.objects.filter(ticker__iexact=t).first()

    def handle_no_instrument(self):
        messages.error(self.request, f"Инструмент «{self.get_ticker()}» не найден.")
        return redirect("mm08:instrument_list")

    def dispatch(self, request, *args, **kwargs):
        self.instrument = self.get_instrument()
        if self.instrument is None:
            return self.handle_no_instrument()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = getattr(super(), "get_context_data", lambda **kw: {})(**kwargs)
        ctx[self.instrument_context_name] = self.instrument
        return ctx


# ---------- PAGES (CBV) ----------
class HomeView(TemplateView):
    template_name = "mm08/index.html"

    def get_context_data(self, **kwargs):
        return {"title": "MM08 — старт"}


class InstrumentListView(ListView):
    model = Instrument
    template_name = "mm08/instruments.html"
    context_object_name = "instruments"
    queryset = Instrument.objects.order_by("ticker")


class InstrumentCreateView(CreateView):
    model = Instrument
    form_class = InstrumentForm
    template_name = "mm08/instrument_form.html"
    success_url = reverse_lazy("mm08:instrument_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = "Добавить инструмент"
        return ctx


class CandleFilterView(FormView):
    template_name = "mm08/candle_filter.html"
    form_class = CandleFilterForm

    def form_valid(self, form):
        inst = form.cleaned_data["instrument"]
        interval = form.cleaned_data["interval"]
        url = reverse("mm08:candle_list", args=[inst.ticker])
        return HttpResponseRedirect(f"{url}?interval={interval}")

    def get_context_data(self, **kwargs):
        return {"title": "Фильтр свечей", "form": self.get_form()}


class CandleListView(InstrumentByTickerMixin, ListView):
    """Список свечей по инструменту."""
    model = Candle
    template_name = "mm08/candles.html"
    context_object_name = "candles"
    paginate_by = None  # если понадобится пагинация — поставь число

    def get_queryset(self):
        qs = Candle.objects.filter(instrument=self.instrument)
        interval = self.request.GET.get("interval")
        if interval:
            qs = qs.filter(interval=interval)
        return qs.order_by("-dt")[:500]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = f"Свечи {self.instrument.ticker}"
        return ctx


class ChartView(InstrumentByTickerMixin, TemplateView):
    template_name = "mm08/chart.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = f"График {self.instrument.ticker}"
        ctx["interval"] = self.request.GET.get("interval", "60")
        return ctx


class ChartDataView(InstrumentByTickerMixin, View):
    """JSON для графика (как было, только CBV)."""
    def get(self, request, *args, **kwargs):
        interval = int(request.GET.get("interval", 60))
        qs = (Candle.objects
              .filter(instrument=self.instrument, interval=interval)
              .order_by("dt")
              .values("dt", "open", "high", "low", "close", "volume")[:5000])
        data = [{"t": c["dt"].isoformat(), "o": c["open"], "h": c["high"],
                 "l": c["low"], "c": c["close"], "v": c["volume"]} for c in qs]
        return JsonResponse({"data": data})


class DashboardView(TemplateView):
    template_name = "mm08/dashboard.html"

    def get_context_data(self, **kwargs):
        instruments = Instrument.objects.filter(is_active=True).order_by("ticker")
        last_dt_map = (Candle.objects
                       .values("instrument__ticker")
                       .annotate(last_dt=Max("dt"))
                       .order_by())
        last_dt_dict = {row["instrument__ticker"]: row["last_dt"] for row in last_dt_map}
        rows = [{"ticker": inst.ticker,
                 "shortname": inst.shortname,
                 "market": inst.market,
                 "last_dt": last_dt_dict.get(inst.ticker)} for inst in instruments]
        return {"title": "Дашборд", "total_active": instruments.count(), "rows": rows}


# ---------- НОВАЯ СТРАНИЦА: карточка инструмента ----------
class InstrumentDetailView(InstrumentByTickerMixin, DetailView):
    """Карточка инструмента + последние 50 свечей."""
    model = Instrument
    template_name = "mm08/instrument_detail.html"
    context_object_name = "instrument"

    # DetailView по умолчанию ждёт pk/slug; используем миксин:
    def get_object(self, queryset=None):
        return self.instrument

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = f"{self.instrument.ticker} — карточка"
        ctx["last_candles"] = (Candle.objects
                               .filter(instrument=self.instrument)
                               .order_by("-dt")[:50])
        return ctx
