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

from .models import Instrument, Candle, HeatSnapshot, HeatTile
from .forms import CandleFilterForm, InstrumentCreateForm


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
        # Миксин только кладёт объект инструмента в контекст
        ctx = super().get_context_data(**kwargs)
        ctx[self.instrument_context_name] = self.instrument
        return ctx


# ---------- PAGES (CBV) ----------
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

    # чтобы миксин НЕ бросал PermissionDenied
    raise_exception = False

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
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
    """Список свечей по инструменту."""
    model = Candle
    template_name = "mm08/candles.html"
    context_object_name = "candles"
    paginate_by = None  # при необходимости можно включить пагинацию

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
    """JSON для графика."""
    def get(self, request, *args, **kwargs):
        interval = int(request.GET.get("interval", 60))
        qs = (Candle.objects
              .filter(instrument=self.instrument, interval=interval)
              .order_by("dt")
              .values("dt", "open", "high", "low", "close", "volume")[:5000])
        data = [{"t": c["dt"].isoformat(), "o": c["open"], "h": c["high"],
                 "l": c["low"], "c": c["close"], "v": c["volume"]} for c in qs]
        return JsonResponse({"data": data})


class DashboardView(LoginRequiredMixin, TemplateView):
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


class InstrumentDetailView(InstrumentByTickerMixin, DetailView):
    """Карточка инструмента + последние 50 свечей."""
    model = Instrument
    template_name = "mm08/instrument_detail.html"
    context_object_name = "instrument"

    def get_object(self, queryset=None):
        return self.instrument

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = f"{self.instrument.ticker} — карточка"
        ctx["last_candles"] = (Candle.objects
                               .filter(instrument=self.instrument)
                               .order_by("-dt")[:50])
        return ctx


def custom_permission_denied(request, exception=None):
    """Дружелюбная страница 403."""
    response = render(request, "mm08/403.html", status=403)
    response.status_code = 403
    return response


# ---------- HEATMAP ----------
def _color_by_change(pct, *, neutral_when_abs_lt: float = 0.01) -> str:
    """
    Цвет плитки по % изменения.
    - None и |pct| < neutral_when_abs_lt -> нейтральный серый.
    - < 0 -> красный (темнее при большем модуле).
    - > 0 -> зелёный (темнее при большем модуле).
    """
    try:
        if pct is None:
            return "#374151"  # нейтральный, нет данных
        v = float(pct)
    except (TypeError, ValueError):
        return "#374151"

    if abs(v) < neutral_when_abs_lt:
        return "#374151"

    # ограничим диапазон для визуала
    v = max(min(v, 10.0), -10.0)
    strength = abs(v) / 10.0  # 0..1

    hue = 120 if v > 0 else 0
    sat = int(30 + 70 * strength)      # 30..100
    light = int(52 - 20 * strength)    # 52..32 (чем сильнее – тем темнее)

    return f"hsl({hue}, {sat}%, {light}%)"


def window_numbers(page_obj, window=5):
    """Вернуть список номеров страниц длиной ≤ window, центрируя текущую."""
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
        pk = self.kwargs.get("pk")
        board = self.request.GET.get("board") or "TQBR"
        date_s = self.request.GET.get("date")
        label = self.request.GET.get("label") or ""  # fast/fresh/…

        qs = HeatSnapshot.objects.filter(board=board).order_by("-created_at")
        if pk:
            return qs.select_related().prefetch_related("tiles").get(pk=pk)

        if date_s:
            try:
                dt = timezone.datetime.fromisoformat(date_s)
                qs = qs.filter(created_at__date=dt.date())
            except Exception:
                pass
        if label:
            qs = qs.filter(label=label)

        return qs.select_related().prefetch_related(
            Prefetch("tiles", queryset=HeatTile.objects.order_by("-change_pct"))
        ).first()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        board = self.request.GET.get("board") or "TQBR"

        # размер страницы
        per_choices = [5, 10, 20, 50]
        try:
            per = int((self.request.GET.get("per") or "20").strip())
        except ValueError:
            per = 20
        if per not in per_choices:
            per = 20

        snap = self.get_snapshot()
        tiles_qs = snap.tiles.order_by("-change_pct") if snap else HeatTile.objects.none()

        # подготовка карточек
        prepped = []
        for t in tiles_qs:
            try:
                is_up = (t.change_pct is not None) and (float(t.change_pct) > 0)
            except (TypeError, ValueError):
                is_up = False
            prepped.append({
                "ticker": t.ticker,
                "shortname": t.shortname,
                "change_pct": t.change_pct,
                "last": t.last,
                "turnover": t.turnover,
                "bg": _color_by_change(t.change_pct),
                "is_up": is_up,
            })

        # пагинация
        paginator = Paginator(prepped, per)
        page_num = self.request.GET.get("page", "1")
        try:
            page = paginator.page(page_num)
        except EmptyPage:
            page = paginator.page(paginator.num_pages)
        except Exception:
            page = paginator.page(1)

        # для выпадающего списка дат
        last_dates = (HeatSnapshot.objects
                      .filter(board=board)
                      .order_by("-created_at")
                      .values_list("created_at", flat=True)[:20])

        ctx.update({
            "title": "Теплокарты MOEX",
            "board": board,
            "snapshot": snap,
            "tiles": page.object_list,
            "page_obj": page,
            "paginator": paginator,
            "page_numbers": window_numbers(page, 5),
            "per": per,
            "per_choices": per_choices,
            "dates": [d.date() for d in last_dates],
        })
        return ctx


class HeatmapRefreshView(PermissionRequiredMixin, View):
    """Обновить теплокарту с MOEX и редирект на страницу."""
    permission_required = "mm08.add_heatsnapshot"

    def post(self, request, *args, **kwargs):
        from .management.commands.load_heatmap import fetch_board
        board = request.POST.get("board", "TQBR")
        label = request.POST.get("label", "fast")
        rows = fetch_board(board=board)
        if not rows:
            messages.error(request, "Не удалось получить данные с MOEX.")
            return redirect("mm08:heatmap")

        snap = HeatSnapshot.objects.create(board=board, label=label)
        HeatTile.objects.bulk_create([
            HeatTile(
                snapshot=snap,
                ticker=r["ticker"],
                shortname=r["shortname"],
                last=r["last"] or 0,
                change_pct=r["change_pct"],        # может быть None — это ок
                turnover=r["turnover"] or 0,
                volume=r["volume"] or 0,
                lot_size=r["lot_size"] or 1,
            )
            for r in rows
        ])
        messages.success(request, f"Обновлено: {board} ({label}), {len(rows)} тикеров.")
        return redirect("mm08:heatmap")

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


class HeatmapExportView(View):
    """Экспорт текущего среза в CSV."""
    def get(self, request, *args, **kwargs):
        board = request.GET.get("board") or "TQBR"
        snap = (HeatSnapshot.objects
                .filter(board=board)
                .order_by("-created_at")
                .prefetch_related("tiles")
                .first())
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
