# mm08/views.py
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator, EmptyPage
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView, ListView, FormView, DetailView
from django.shortcuts import redirect, render
from django.db.models import Max, Prefetch
from django.db import transaction

from decimal import Decimal
import json

from .models import Instrument, Candle, HeatSnapshot, HeatTile
from .forms import CandleFilterForm, InstrumentCreateForm


# ---------- MIXINS ----------
class InstrumentByTickerMixin:
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
        ctx = super().get_context_data(**kwargs)
        ctx[self.instrument_context_name] = self.instrument
        return ctx


# ---------- PAGES ----------
class HomeView(TemplateView):
    template_name = "mm08/index.html"

    def get_context_data(self, **kwargs):
        return {"title": "MM08 — старт"}


class InstrumentListView(LoginRequiredMixin, ListView):
    model = Instrument
    template_name = "mm08/instruments.html"
    context_object_name = "instruments"
    queryset = Instrument.objects.order_by("ticker")


class InstrumentCreateView(LoginRequiredMixin, PermissionRequiredMixin, FormView):
    permission_required = "mm08.add_instrument"
    template_name = "mm08/instrument_form.html"
    form_class = InstrumentCreateForm
    success_url = reverse_lazy("mm08:instrument_list")
    raise_exception = False

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(), self.get_login_url(), self.get_redirect_field_name()
            )
        return render(self.request, "mm08/403.html", status=403)

    def get_initial(self):
        return {"engine": "stock", "market": "shares", "board": "TQBR"}

    def form_valid(self, form):
        obj = form.save(user=self.request.user)
        messages.success(self.request, f"Инструмент {obj.ticker} сохранён.")
        return super().form_valid(form)


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


class CandleListView(LoginRequiredMixin, InstrumentByTickerMixin, ListView):
    model = Candle
    template_name = "mm08/candles.html"
    context_object_name = "candles"
    paginate_by = None

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


class ChartView(LoginRequiredMixin, InstrumentByTickerMixin, TemplateView):
    template_name = "mm08/chart.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = f"График {self.instrument.ticker}"
        ctx["interval"] = self.request.GET.get("interval", "60")
        return ctx


class ChartDataView(InstrumentByTickerMixin, View):
    def get(self, request, *args, **kwargs):
        interval = int(request.GET.get("interval", 60))
        qs = (
            Candle.objects.filter(instrument=self.instrument, interval=interval)
            .order_by("dt")
            .values("dt", "open", "high", "low", "close", "volume")[:5000]
        )
        data = [
            {"t": c["dt"].isoformat(), "o": c["open"], "h": c["high"], "l": c["low"], "c": c["close"], "v": c["volume"]}
            for c in qs
        ]
        return JsonResponse({"data": data})


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "mm08/dashboard.html"

    def get_context_data(self, **kwargs):
        instruments = Instrument.objects.filter(is_active=True).order_by("ticker")
        last_dt_map = Candle.objects.values("instrument__ticker").annotate(last_dt=Max("dt")).order_by()
        last_dt_dict = {row["instrument__ticker"]: row["last_dt"] for row in last_dt_map}
        rows = [
            {"ticker": inst.ticker, "shortname": inst.shortname, "market": inst.market, "last_dt": last_dt_dict.get(inst.ticker)}
            for inst in instruments
        ]
        return {"title": "Дашборд", "total_active": instruments.count(), "rows": rows}


class InstrumentDetailView(InstrumentByTickerMixin, DetailView):
    model = Instrument
    template_name = "mm08/instrument_detail.html"
    context_object_name = "instrument"

    def get_object(self, queryset=None):
        return self.instrument

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = f"{self.instrument.ticker} — карточка"
        ctx["last_candles"] = Candle.objects.filter(instrument=self.instrument).order_by("-dt")[:50]
        return ctx


def custom_permission_denied(request, exception=None):
    response = render(request, "mm08/403.html", status=403)
    response.status_code = 403
    return response


# ---------- HEATMAP ----------
def _color_by_change(pct, *, neutral_when_abs_lt: float = 0.01) -> str:
    try:
        if pct is None:
            return "#374151"
        v = float(pct)
    except (TypeError, ValueError):
        return "#374151"

    if abs(v) < neutral_when_abs_lt:
        return "#374151"

    v = max(min(v, 10.0), -10.0)
    strength = abs(v) / 10.0
    hue = 120 if v > 0 else 0
    sat = int(30 + 70 * strength)
    light = int(52 - 20 * strength)
    return f"hsl({hue}, {sat}%, {light}%)"


def window_numbers(page_obj, window=5):
    total = page_obj.paginator.num_pages
    cur = page_obj.number
    if total <= window:
        return list(range(1, total + 1))
    half = window // 2
    start = max(1, cur - half)
    end = start + window - 1
    if end > total:
        end = total
        start = max(1, end - window + 1)
    return list(range(start, end + 1))


class HeatmapView(TemplateView):
    template_name = "mm08/heatmaps.html"

    def get_snapshot(self):
        board = self.request.GET.get("board") or "TQBR"
        label = (self.request.GET.get("label") or "").strip()
        date_s = self.request.GET.get("date")

        qs = HeatSnapshot.objects.filter(board=board).order_by("-created_at")
        if label:
            qs = qs.filter(label=label)

        if date_s:
            try:
                dt_ = timezone.datetime.fromisoformat(date_s)
                qs = qs.filter(created_at__date=dt_.date())
            except Exception:
                pass

        return qs.select_related().prefetch_related(
            Prefetch("tiles", queryset=HeatTile.objects.order_by("-change_pct"))
        ).first()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        board = self.request.GET.get("board") or "TQBR"

        per_choices = [5, 10, 20, 50]
        try:
            per = int((self.request.GET.get("per") or "20").strip())
        except ValueError:
            per = 20
        if per not in per_choices:
            per = 20

        snap = self.get_snapshot()
        tiles_qs = snap.tiles.order_by("-change_pct") if snap else HeatTile.objects.none()

        prepped = []
        for t in tiles_qs:
            try:
                is_up = (t.change_pct is not None) and (float(t.change_pct) > 0)
            except (TypeError, ValueError):
                is_up = False
            prepped.append(
                {
                    "ticker": t.ticker,
                    "shortname": t.shortname,
                    "change_pct": t.change_pct,
                    "last": t.last,
                    "turnover": t.turnover,
                    "bg": _color_by_change(t.change_pct),
                    "is_up": is_up,
                }
            )

        paginator = Paginator(prepped, per)
        page_num = self.request.GET.get("page", "1")
        try:
            page = paginator.page(page_num)
        except EmptyPage:
            page = paginator.page(paginator.num_pages)
        except Exception:
            page = paginator.page(1)

        last_dates = (
            HeatSnapshot.objects.filter(board=board).order_by("-created_at").values_list("date", flat=True)[:20]
        )

        ctx.update(
            {
                "title": "Теплокарты MOEX",
                "board": board,
                "snapshot": snap,
                "tiles": page.object_list,
                "page_obj": page,
                "paginator": paginator,
                "page_numbers": window_numbers(page, 5),
                "per": per,
                "per_choices": per_choices,
                "dates": list(last_dates),
            }
        )
        return ctx


class HeatmapRefreshView(PermissionRequiredMixin, View):
    permission_required = "mm08.add_heatsnapshot"

    def post(self, request, *args, **kwargs):
        board = (request.POST.get("board") or "TQBR").upper()
        label = (request.POST.get("label") or "fast").strip()

        # 1) тянем свежие данные с ISS
        engine, market, rows = fetch_board(board)
        if not rows:
            messages.error(request, "Не удалось получить данные с MOEX.")
            return redirect(f"{reverse('mm08:heatmap')}?board={board}&label={label}")

        # 2) снапшот на сегодня (UNIQUE по date/board/label) — обновляем или создаём
        snap_date = timezone.localdate()
        snap, _ = HeatSnapshot.objects.get_or_create(
            date=snap_date, board=board, label=label,
            defaults={"source": "moex"}
        )

        # bump created_at, чтобы на странице было «свежее» время
        snap.created_at = timezone.now()
        snap.source = "moex"
        snap.save(update_fields=["created_at", "source"])

        # 3) перезаписываем плитки
        snap.tiles.all().delete()
        tiles = [
            HeatTile(
                snapshot=snap,
                ticker=r.get("ticker", "")[:20],
                shortname=r.get("shortname", "")[:100],
                engine=engine, market=market, board=board,
                last=r.get("last") or 0,
                change_pct=r.get("change_pct"),   # может быть None
                turnover=r.get("turnover") or 0,
                volume=r.get("volume") or 0,
                lot_size=r.get("lot_size") or 1,
            )
            for r in rows if r.get("ticker")
        ]
        HeatTile.objects.bulk_create(tiles, batch_size=1000)

        messages.success(
            request,
            f"Обновлено: {board} ({label}). Тикеров: {len(tiles)}."
        )
        return redirect(f"{reverse('mm08:heatmap')}?board={board}&label={label}")

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


class HeatmapExportView(View):
    def get(self, request, *args, **kwargs):
        board = request.GET.get("board") or "TQBR"
        snap = (
            HeatSnapshot.objects.filter(board=board).order_by("-created_at").prefetch_related("tiles").first()
        )
        if not snap:
            return HttpResponse("no data", content_type="text/plain", status=404)

        import csv, io

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ticker", "shortname", "last", "change_pct", "turnover", "volume"])
        for t in snap.tiles.order_by("-change_pct"):
            w.writerow([t.ticker, t.shortname, t.last, t.change_pct, t.turnover, t.volume])

        resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = (
            f'attachment; filename="heatmap_{board}_{snap.created_at:%Y%m%d_%H%M}.csv"'
        )
        return resp
