# Project/mm08/views.py
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
from .forms import InstrumentCreateForm, CandleFilterForm
from .services.pagination import window_numbers
from typing import Any


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

    # сколько карточек на страницу (по умолчанию 21)
    DEFAULT_PER_PAGE = 21
    MAX_PER_PAGE = 200

    def _parse_int(self, s: str | None, default: int, upper: int | None = None) -> int:
        try:
            v = int(s) if s else default
            if upper is not None:
                v = min(v, upper)
            return max(1, v)
        except Exception:
            return default

    def _pick_snapshot(self, board: str, label: str, date_s: str) -> "HeatSnapshot | None":
        """
        Выбираем снапшот:
          1) если переданы date/label — пробуем строго по ним,
          2) иначе берём ЛЮБОЙ последний по board,
          3) если по п.1 ничего не нашли — откатываемся к п.2 (чтобы не было пусто).
        Обязательно префетчим плитки, отсортированные по change_pct.
        """
        # базовый QS снапшотов
        qs = HeatSnapshot.objects.filter(board=board).only("id", "board", "label", "date", "created_at")

        # применяем фильтры, если заданы
        filtered = qs
        if label:
            filtered = filtered.filter(label=label)

        if date_s:
            from django.utils.dateparse import parse_date, parse_datetime
            dt = parse_date(date_s) or (parse_datetime(date_s).date() if parse_datetime(date_s) else None)
            if dt:
                filtered = filtered.filter(date=dt)

        # порядок — от новых к старым
        filtered = filtered.order_by("-date", "-created_at")
        base_ordered = qs.order_by("-date", "-created_at")

        # подготавливаем префетч плиток
        tiles_qs = HeatTile.objects.order_by("-change_pct").only(
            "id", "ticker", "shortname", "last", "change_pct", "turnover", "volume", "snapshot_id"
        )
        pref = Prefetch("tiles", queryset=tiles_qs)

        snap = filtered.prefetch_related(pref).first()
        if snap is None:
            # fallback: самый последний вообще, чтобы страница не была пустой
            snap = base_ordered.prefetch_related(pref).first()
        return snap

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        ctx = super().get_context_data(**kwargs)

        board = (self.request.GET.get("board") or "TQBR").strip()
        label = (self.request.GET.get("label") or "").strip()
        date_s = (self.request.GET.get("date") or "").strip()
        per_page = self._parse_int(self.request.GET.get("per"), self.DEFAULT_PER_PAGE, self.MAX_PER_PAGE)

        snapshot = self._pick_snapshot(board=board, label=label, date_s=date_s)

        tiles_list: list["HeatTile"] = []
        if snapshot is not None:
            # материализуем список плиток один раз, чтоб шаблон не гонял БД
            tiles_list = list(snapshot.tiles.all())

        # пагинация
        from django.core.paginator import Paginator, EmptyPage
        paginator = Paginator(tiles_list, per_page)
        page_num = self.request.GET.get("page") or 1
        try:
            page_obj = paginator.page(page_num)
        except EmptyPage:
            page_obj = paginator.page(1)

        ctx.update(
            {
                "title": "Теплокарты MOEX",
                "board": board,
                "label": label,
                "date": date_s,
                "snapshot": snapshot,
                "page_obj": page_obj,
                "per": per_page,
                "total_tiles": len(tiles_list),
            }
        )
        return ctx

class HeatmapRefreshView(LoginRequiredMixin, View):
    """
    Обновление/пересборка снапшота теплокарты.
    GET/POST-параметры:
      - board: код доски (по умолчанию "TQBR")
      - label: метка снапшота (напр. "fast"/"fresh"/"manual")
      - replace: "1"/"true"/"yes" → перезаписать существующий снимок за СЕГОДНЯ (по умолчанию ВКЛ)
      - redirect: "1" → после сборки сделать 302 на /heatmaps/?board=...&label=...
    """

    def _do(self, request):
        # читаем из POST в приоритете (кнопки-формы), затем из GET
        board = (request.POST.get("board") or request.GET.get("board") or "TQBR").strip()
        label = (request.POST.get("label") or request.GET.get("label") or "").strip()

        # по умолчанию разрешаем перезапись (чтобы кнопки без replace работали ожидаемо)
        replace_raw = (request.POST.get("replace") or request.GET.get("replace") or "1").strip().lower()
        replace = replace_raw in ("1", "true", "yes", "y")

        need_redirect = (request.POST.get("redirect") or request.GET.get("redirect") or "").strip() in ("1", "true", "yes", "y")

        try:
            from .services.heatmap import build_snapshot
        except Exception:
            return JsonResponse(
                {
                    "status": "not_implemented",
                    "board": board,
                    "label": label,
                    "hint": "Добавьте mm08/services/heatmap.py с функцией build_snapshot(board, label, replace).",
                },
                status=501,
                json_dumps_params={"ensure_ascii": False},
            )

        try:
            snapshot, created = build_snapshot(board=board, label=label, replace=replace)

            if need_redirect:
                from django.shortcuts import redirect
                from django.urls import reverse
                url = f"{reverse('mm08:heatmaps')}?board={board}"
                if label:
                    url += f"&label={label}"
                return redirect(url)

            return JsonResponse(
                {
                    "status": "ok",
                    "board": board,
                    "label": label or "manual",
                    "replace": replace,
                    "created": created,
                    "snapshot_id": snapshot.id,
                    "date": str(getattr(snapshot, "date", "")),
                },
                json_dumps_params={"ensure_ascii": False},
            )
        except Exception as e:
            return JsonResponse(
                {"status": "error", "board": board, "label": label, "error": f"build_snapshot failed: {e}"},
                status=500,
                json_dumps_params={"ensure_ascii": False},
            )

    def get(self, request, *args, **kwargs):
        return self._do(request)

    def post(self, request, *args, **kwargs):
        return self._do(request)

    
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