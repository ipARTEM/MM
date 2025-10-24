# Project/mm08/views.py
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.paginator import Paginator, EmptyPage
from django.http import JsonResponse, HttpResponseRedirect, HttpResponse, HttpRequest
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views import View
from django.views.generic import TemplateView, ListView, FormView, DetailView
from django.shortcuts import redirect, render
from django.db.models import Max, Prefetch
from django.db import transaction

from typing import Any, Dict, List
from django.http import HttpRequest
from django.utils import timezone
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin


from decimal import Decimal
import json

from .models import Instrument, Candle, HeatSnapshot, HeatTile
from .forms import InstrumentCreateForm, CandleFilterForm
from .services.pagination import window_numbers
from .services.heatmap import build_snapshot  #  функция сборки
from mm08.services.iss_client import fetch_tqbr_all

from typing import Any, Dict, List


# ---------- MIXINS ----------
class InstrumentByTickerMixin:
    instrument_context_name = "instrument"

    def dispatch(self, request, *args, **kwargs):
        ticker = kwargs.get("ticker")
        try:
            self.instrument = Instrument.objects.get(ticker=ticker)
        except Instrument.DoesNotExist:
            messages.error(request, f"Инструмент {ticker} не найден")
            return redirect("mm08:instrument_list")
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


class DashboardView(LoginRequiredMixin, TemplateView):
    # шаблон страницы дашборда
    template_name = "mm08/dashboard.html"

    def get_context_data(self, **kwargs):
        # базовый контекст
        ctx = super().get_context_data(**kwargs)

        # Простейшие данные для виджетов (без тяжёлых запросов)
        total_instruments = Instrument.objects.count()                # количество инструментов
        latest_candle = (Candle.objects
                         .only("dt")
                         .order_by("-dt")
                         .first())                                    # последняя дата свечей

        ctx.update({
            "title": "Дашборд",
            "total_instruments": total_instruments,
            "latest_candle_dt": latest_candle.dt if latest_candle else None,
        })
        return ctx


class InstrumentListView(LoginRequiredMixin, ListView):
    model = Instrument
    template_name = "mm08/instruments.html"
    context_object_name = "instruments"
    queryset = Instrument.objects.order_by("ticker")


class InstrumentDetailView(InstrumentByTickerMixin, DetailView):
    model = Instrument
    template_name = "mm08/instrument_detail.html"
    context_object_name = "instrument"

    def get_object(self, queryset=None):
        return self.instrument


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
        return render(
            self.request,
            "mm08/403.html",
            status=403,
            context={"title": "Недостаточно прав", "message": "У вас нет разрешения на это действие"},
        )


class CandleFilterView(LoginRequiredMixin, FormView):
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
        # ✅ Убираем N+1: подгружаем связанный instrument одной выборкой
        qs = Candle.objects.filter(instrument=self.instrument).select_related("instrument")
        interval = self.request.GET.get("interval")
        if interval:
            qs = qs.filter(interval=interval)
        return qs.order_by("-dt")[:500]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["title"] = f"Свечи {self.instrument.ticker}"
        return ctx

class ChartView(LoginRequiredMixin, InstrumentByTickerMixin, TemplateView):
    # шаблон страницы графика
    template_name = "mm08/chart.html"

    # Контекст шаблона
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)   # базовый контекст
        ctx["title"] = f"График {self.instrument.ticker}"  # заголовок
        ctx["ticker"] = self.instrument.ticker            # тикер для фронта/JS
        # можно прокидывать интервал в график через GET (?interval=M1)
        ctx["interval"] = self.request.GET.get("interval") or "M1"
        return ctx

class ChartDataView(LoginRequiredMixin, InstrumentByTickerMixin, View):
    """
    Отдаёт данные свечей по инструменту в JSON для графика.
    Параметры (GET):
      - interval: строка, например M1/M5/H1/D1 (по умолчанию M1)
      - limit: количество точек (1..5000), по умолчанию 500
      - date_from / date_to: ISO-строки (YYYY-MM-DD или ISO datetime), опционально
    """
    def get(self, request, *args, **kwargs):
        interval = (request.GET.get("interval") or "M1").strip()
        limit_s  = (request.GET.get("limit") or "500").strip()
        date_from = (request.GET.get("date_from") or "").strip()
        date_to   = (request.GET.get("date_to") or "").strip()

        # безопасно парсим limit
        try:
            limit = max(1, min(int(limit_s), 5000))
        except Exception:
            limit = 500

        qs = (Candle.objects
              .filter(instrument=self.instrument)
              .select_related("instrument"))

        if interval:
            qs = qs.filter(interval=interval)

        # фильтры по дате при наличии
        from django.utils.dateparse import parse_datetime
        from datetime import datetime as _dt

        if date_from:
            try:
                dt_from = _dt.fromisoformat(date_from + " 00:00:00") if len(date_from) == 10 else parse_datetime(date_from)
                if dt_from:
                    qs = qs.filter(dt__gte=dt_from)
            except Exception:
                pass

        if date_to:
            try:
                dt_to = _dt.fromisoformat(date_to + " 23:59:59") if len(date_to) == 10 else parse_datetime(date_to)
                if dt_to:
                    qs = qs.filter(dt__lte=dt_to)
            except Exception:
                pass

        # берём последние limit штук, сортируем по возрастанию времени для корректного графика
        candles = list(
            qs.order_by("-dt")[:limit]
              .values("dt", "interval", "open", "high", "low", "close", "volume")
        )
        candles.reverse()

        data = {
            "ticker": self.instrument.ticker,
            "interval": interval,
            "count": len(candles),
            "candles": candles,
        }
        return JsonResponse(data, json_dumps_params={"ensure_ascii": False})


# ---------- HEATMAP ----------
class HeatmapView(LoginRequiredMixin, TemplateView):
    template_name = "mm08/heatmaps.html"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)

        board = (self.request.GET.get("board") or "TQBR").upper()
        label = (self.request.GET.get("label") or "").strip()
        per = int(self.request.GET.get("per") or 42)

        # берем последний снимок по доске/метке (если метка не задана — любой)
        qs = HeatSnapshot.objects.filter(board=board).order_by("-date", "-created_at")
        if label:
            qs = qs.filter(label=label)
        snapshot = qs.first()

        tiles = HeatTile.objects.none()
        if snapshot:
            tiles = HeatTile.objects.filter(snapshot=snapshot).order_by("-change_pct", "ticker")

        # простая пагинация руками
        from django.core.paginator import Paginator
        paginator = Paginator(tiles, per)
        page = int(self.request.GET.get("page") or 1)
        page_obj = paginator.get_page(page)
        page_nums = window_numbers(page_obj.number, paginator.num_pages, 5)

        ctx.update(
            board=board,
            snapshot=snapshot,
            tiles=page_obj.object_list,
            paginator=paginator,
            page_obj=page_obj,
            page_numbers=page_nums,
            per=per,
            per_choices=[21, 42, 84],
            date=snapshot.date if snapshot else "",
        )
        return ctx

class HeatmapRefreshView(LoginRequiredMixin, View):
    """POST: подтянуть данные с MOEX, собрать/обновить снимок, вернуть JSON или редирект."""
    def post(self, request, *args, **kwargs):
        board = (request.POST.get("board") or request.GET.get("board") or "TQBR").strip().upper()
        label = (request.POST.get("label") or request.GET.get("label") or "fast").strip()
        date_s = (request.POST.get("date") or request.GET.get("date") or "").strip()
        replace = True  # пересобираем плитки, чтобы получить свежие котировки

        try:
            snapshot, created = build_snapshot(board=board, label=label, date=date_s or None, replace=replace)
        except Exception as exc:
            return JsonResponse(
                {
                    "status": "error",
                    "board": board,
                    "label": label,
                    "error": f"build_snapshot failed: {exc}",
                },
                status=500,
            )

        # Если в форме есть скрытый redirect=1 — вернёмся на список
        if request.POST.get("redirect") == "1" or request.GET.get("redirect") == "1":
            return HttpResponseRedirect(f"/heatmaps/?board={board}&label={label}")

        return JsonResponse(
            {
                "status": "ok",
                "board": board,
                "label": label,
                "replace": replace,
                "created": created,
                "snapshot_id": snapshot.id,
                "date": str(snapshot.date),
            }
        )

    
class HeatmapExportView(LoginRequiredMixin, View):
    """
    Экспорт текущего снапшота теплокарты в CSV.
    GET-параметры:
      - board: код доски, по умолчанию 'TQBR'
      - label: метка снапшота (например: 'fast'/'fresh'/'close'), опционально
      - date:  YYYY-MM-DD — если нужен снапшот конкретной даты (опционально)
    Столбцы CSV: ticker, shortname, last, change_pct, turnover, volume.
    Если нужного поля нет — пишем пустое значение.
    """
    def get(self, request, *args, **kwargs):
        board = (request.GET.get("board") or "TQBR").strip()
        label = (request.GET.get("label") or "").strip()
        date_s = (request.GET.get("date") or "").strip()

        # Локальная функция: получить снапшот примерно так же, как в HeatmapView.get_snapshot()
        def _get_snapshot():
            qs = HeatSnapshot.objects.filter(board=board).order_by("-created_at")
            if label:
                qs = qs.filter(label=label)

            if date_s:
                try:
                    # если пришла только дата (YYYY-MM-DD) — используем день целиком
                    if len(date_s) == 10:
                        from datetime import datetime, time
                        d = datetime.fromisoformat(date_s).date()
                        start = datetime.combine(d, time.min)
                        end = datetime.combine(d, time.max)
                        qs = qs.filter(created_at__range=(start, end))
                    else:
                        # иначе доверяем ISO-датавремени и фильтруем "после"
                        from django.utils.dateparse import parse_datetime
                        dt = parse_datetime(date_s)
                        if dt:
                            qs = qs.filter(created_at__gte=dt)
                except Exception:
                    pass

            # Важно: НЕ урезаем поля у плиток, чтобы не словить ленивые догрузки
            tiles_qs = HeatTile.objects.order_by("-change_pct")
            return qs.only("id", "board", "label", "created_at") \
                    .prefetch_related(Prefetch("tiles", queryset=tiles_qs)) \
                    .first()

        snap = _get_snapshot()
        if not snap:
            return JsonResponse(
                {"error": "Не найден снапшот теплокарты под заданные параметры"},
                status=404,
                json_dumps_params={"ensure_ascii": False},
            )

        # Готовим CSV-ответ
        import csv
        from io import StringIO
        buf = StringIO()
        writer = csv.writer(buf, lineterminator="\n")

        # Заголовки CSV
        headers = ["ticker", "shortname", "last", "change_pct", "turnover", "volume"]
        writer.writerow(headers)

        # Данные
        tiles = snap.tiles.all()
        for t in tiles:
            # безопасно читаем поля (если нет — пишем пустое)
            row = [
                getattr(t, "ticker", "") or "",
                getattr(t, "shortname", "") or "",
                getattr(t, "last", ""),
                getattr(t, "change_pct", ""),
                getattr(t, "turnover", ""),
                getattr(t, "volume", ""),
            ]
            writer.writerow(row)

        csv_text = buf.getvalue()
        buf.close()

        # Формируем HTTP-ответ
        filename = f"heatmap_{board}_{label or 'latest'}.csv"
        resp = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp
    
def custom_permission_denied(request, exception=None):
    """
    Кастомный обработчик 403 Forbidden.
    Вызывается, когда у пользователя нет прав на действие/страницу.
    """
    context = {
        "title": "Недостаточно прав",
        "message": "У вас нет разрешения на просмотр этой страницы.",
    }
    # используем шаблон templates/mm08/403.html
    return render(request, "mm08/403.html", context=context, status=403)

class StocksHeatmapView(LoginRequiredMixin, TemplateView):
    # Страница "Теплокарта Акции": кнопка "Скачать данные по Акциям" + таблица
    template_name = "mm08/heatmap_stocks.html"          # путь к шаблону

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        # GET: показываем пустую таблицу и скрытую строку среза
        ctx = super().get_context_data(**kwargs)        # базовый контекст
        ctx["board"] = "TQBR"                           # фиксируем доску TQBR
        ctx["snapshot_text"] = ""                       # пока нет среза
        ctx["rows"] = []                                # пустые данные
        return ctx                                      # отдаём контекст

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any):
        # POST: тянем данные с ISS, собираем таблицу и формируем строку "Срез: ..."
        context = self.get_context_data(**kwargs)       # получаем базовый контекст
        rows: List[dict] = fetch_tqbr_all()             # тянем все страницы по TQBR
        now = timezone.localtime()                      # локализованное текущее время
        # Формируем строку "Срез: TQBR на DD.MM.YYYY HH:MM"
        context["snapshot_text"] = f"Срез: TQBR на {now.strftime('%d.%m.%Y %H:%M')}"  # человекочитаемая дата
        context["rows"] = rows                          # кладём данные для таблицы
        return self.render_to_response(context)         # рендерим шаблон
    

class StocksListView(LoginRequiredMixin, TemplateView):
    template_name = "mm08/stocks_list.html"

    def get_context_data(self, **kwargs: Any) -> Dict[str, Any]:
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("rows", [])
        ctx.setdefault("slice", None)
        ctx.setdefault("error", None)
        return ctx

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any):
        from .services.iss_client import fetch_tqbr_all  # локальный импорт, чтобы не тащить при старте

        ctx = self.get_context_data()
        try:
            raw: List[dict] = fetch_tqbr_all()  # secid/shortname/last/change_pct/board (нижний регистр)

            # Нормализуем ключи под единый формат, безопасно достаём значения
            rows: List[Dict[str, Any]] = [
                {
                    "SECID": r.get("secid"),
                    "SHORTNAME": r.get("shortname"),
                    "BOARD": r.get("board"),
                    "LAST": r.get("last"),
                    "CHANGE_PCT": r.get("change_pct"),  # может быть None
                }
                for r in raw
            ]

            # Сортировка: сначала те, где есть значение, затем по убыванию процента
            rows.sort(key=lambda x: (x["CHANGE_PCT"] is None, -(x["CHANGE_PCT"] or 0)))

            ctx["rows"] = rows
            ctx["snapshot"] = {
                "board": "TQBR",
                "ts": timezone.localtime(),  # время «среза» (когда скачали)
            }
        except Exception as e:
            ctx["error"] = f"{type(e).__name__}: {e}"

        return self.render_to_response(ctx)