# MM/mm08/api_views.py
# ─────────────────────────────────────────────────────────────────────────────
# Путь и имя файла: MM/mm08/api_views.py
# Назначение: DRF-представления (ViewSet’ы) для API приложения mm08
# ─────────────────────────────────────────────────────────────────────────────


from __future__ import annotations  # поддержка современных аннотаций

# ===== БАЗОВЫЕ ИМПОРТЫ =========================================================
from datetime import datetime  # для парсинга дат
from typing import Any, Dict, Optional  # типы для подсказок

from django.http import JsonResponse  # возврат JSON
from django.utils.dateparse import parse_datetime  # парсинг ISO-дат
from django.shortcuts import get_object_or_404  # 404-хелпер
from django.views.decorators.http import require_GET  # ограничим методы на функциях

from rest_framework import viewsets, mixins  # базовые классы DRF
from rest_framework.decorators import action  # экшены у ViewSet
from rest_framework.response import Response  # DRF-ответ
from rest_framework.pagination import PageNumberPagination  # пагинация DRF

# ===== НАШИ МОДЕЛИ И СЕРИАЛИЗАТОРЫ ============================================
from .models import Instrument, Candle, HeatSnapshot, HeatTile   # модели
from .serializers import (
    InstrumentSerializer,   # сериализатор инструмента  
    CandleSerializer,       # сериализатор свечей       
    HeatSnapshotSerializer,                 # сериализатор снапшота (без tiles)  
    HeatSnapshotWithTilesSerializer,        # сериализатор снапшота (с tiles)     
    HeatTileSerializer,                     # сериализатор плитки теплокарты 
)  # импорт сериализаторов 


class HeatSnapshotViewSet(mixins.ListModelMixin,
                          mixins.RetrieveModelMixin,
                          viewsets.GenericViewSet):
    """ViewSet для списка и детального просмотра снимков теплокарты."""
    queryset = HeatSnapshot.objects.all().order_by("-date", "-created_at")  # базовый QuerySet  
    serializer_class = HeatSnapshotSerializer                              # сериализатор по умолчанию 
    # pagination_class = DefaultPagination  # ← включаем пагинацию для списка снапшотов 

    @action(detail=True, methods=["get"])
    def tiles(self, request, pk: int | str | None = None) -> Response:
        """Отдать все плитки для конкретного снапшота (pk из URL)."""
        snapshot = get_object_or_404(HeatSnapshot, pk=pk)              # получаем снапшот  
        qs = snapshot.tiles.all().order_by("-change_pct")               # берём связанные плитки  
        page = self.paginate_queryset(qs)                               # применяем пагинацию  
        if page is not None:                                            # если есть страница  
            ser = HeatTileSerializer(page, many=True)                   # сериализуем страницу  
            return self.get_paginated_response(ser.data)                # отдаём с метаданными пагинации  
        ser = HeatTileSerializer(qs, many=True)                         # сериализуем без пагинации  
        return Response(ser.data)                                       # обычный ответ  

    def retrieve(self, request, *args: Any, **kwargs: Any) -> Response:
        """Переопределяем retrieve, чтобы отдавать снапшот сразу с 'tiles' (удобно в UI)."""
        self.serializer_class = HeatSnapshotWithTilesSerializer         # временно меняем сериализатор  
        return super().retrieve(request, *args, **kwargs)               # зовём базовую реализацию  

class HeatTileViewSet(mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    """ViewSet для плиток теплокарты (общий список и детальный просмотр)."""
    queryset = HeatTile.objects.select_related("snapshot").all().order_by("-change_pct")  # оптимизация связей  # ← комментарий
    serializer_class = HeatTileSerializer  




# ===== СЕРВИСЫ ДЛЯ MOEX (КАТАЛОГ И МЕТАДАННЫЕ) ================================
from .services.moex_catalog import get_moex_info, get_moex_list  # инфо и списки
from .services.moex_meta import (  # справочники + проверка валидности связки
    get_markets,
    get_boards,
    get_engines,
    get_defaults,
    is_valid_combo,
)

# ===== ОПЦИОНАЛЬНЫЕ СЕРВИСЫ ДЛЯ ОПЦИОНОВ ======================================
# Импортируем безопасно: если файла нет — эндпойнт вернёт 501 с понятной ошибкой.
try:
    from .services.moex_options import get_options, get_strikes  # список опционов и страйков
except Exception:
    get_options = None  # type: ignore
    get_strikes = None  # type: ignore

# ==============================================================================
#                               ПАГИНАЦИЯ DRF
# ==============================================================================
class DefaultPagination(PageNumberPagination):
    """Стандартная пагинация: по умолчанию 50, через ?page_size= можно менять (до max=500)."""
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


# ==============================================================================
#                          VIEWSET ДЛЯ ИНСТРУМЕНТОВ
# ==============================================================================
class InstrumentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Список/деталь инструментов."""
    serializer_class = InstrumentSerializer
    queryset = Instrument.objects.all().order_by("ticker")


# ==============================================================================
#                              VIEWSET ДЛЯ СВЕЧЕЙ
# ==============================================================================
class CandleViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Список свечей с фильтрами (?instrument=, ?date_from=, ?date_to=)."""
    serializer_class = CandleSerializer
    pagination_class = DefaultPagination

    def get_queryset(self):
        """
        Базовый queryset.
        ВАЖНО: select_related('instrument') — предотвращает N+1 при сериализации
        (в CandleSerializer поле instrument — SlugRelatedField).
        """
        qs = Candle.objects.select_related("instrument")  # подгружаем FK одной выборкой

        # --- Фильтр по инструменту (тикер) ---
        instrument = self.request.GET.get("instrument")
        if instrument:
            inst = get_object_or_404(Instrument, ticker=instrument)
            qs = qs.filter(instrument=inst)

        # --- Фильтры по датам ---
        date_from = self.request.GET.get("date_from")
        date_to = self.request.GET.get("date_to")

        if date_from:
            try:
                if len(date_from) == 10:
                    date_from_dt = datetime.fromisoformat(date_from + " 00:00:00")
                else:
                    date_from_dt = parse_datetime(date_from)
                if date_from_dt:
                    qs = qs.filter(dt__gte=date_from_dt)
            except Exception:
                pass

        if date_to:
            try:
                if len(date_to) == 10:
                    date_to_dt = datetime.fromisoformat(date_to + " 23:59:59")
                else:
                    date_to_dt = parse_datetime(date_to)
                if date_to_dt:
                    qs = qs.filter(dt__lte=date_to_dt)
            except Exception:
                pass

        return qs.order_by("-dt")

    @action(detail=False, methods=["get"])
    def latest(self, request):
        """Вернуть последние N свечей. Параметры: ?instrument=..., ?limit= (<=500)."""
        instrument = request.GET.get("instrument")
        limit_s = request.GET.get("limit") or "100"
        try:
            limit = max(1, min(int(limit_s), 500))
        except Exception:
            limit = 100

        qs = self.get_queryset()
        if instrument:
            qs = qs.filter(instrument__ticker=instrument)
        qs = qs[:limit]
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


# ==============================================================================
#                      ФУНКЦИОНАЛЬНЫЕ ОБРАБОТЧИКИ ДЛЯ API
# ==============================================================================

@require_GET
def api_moex_meta(request):
    """
    Метаданные MOEX. В сервисах get_defaults/get_markets/get_boards могут требоваться engine/market.
    Делаем вызовы совместимыми независимо от сигнатуры (через try/except TypeError).
    """
    engine = (request.GET.get("engine") or "").strip()
    market = (request.GET.get("market") or "").strip()
    board  = (request.GET.get("board")  or "").strip()

    engines = get_engines()

    # defaults: чаще всего требуют engine
    try:
        defaults = get_defaults(engine)
    except TypeError:
        defaults = get_defaults()

    # markets: с engine, fallback — без
    try:
        markets = get_markets(engine)
    except TypeError:
        markets = get_markets()

    # boards: пробуем engine+market, затем позиционно, затем только market, затем без
    try:
        boards = get_boards(engine=engine, market=market)
    except TypeError:
        try:
            boards = get_boards(engine, market)
        except TypeError:
            try:
                boards = get_boards(market)
            except TypeError:
                boards = get_boards()

    valid_combo: Optional[bool] = None
    if engine or market or board:
        try:
            valid_combo = bool(is_valid_combo(engine=engine, market=market, board=board))
        except Exception:
            valid_combo = None

    data: Dict[str, Any] = {
        "engines": engines,
        "markets": markets,
        "boards": boards,
        "defaults": defaults,
        "combo_check": {"engine": engine, "market": market, "board": board, "is_valid": valid_combo},
    }
    return JsonResponse(data, json_dumps_params={"ensure_ascii": False})


@require_GET
def api_moex_catalog(request):
    """
    Каталог MOEX:
      - если передан ?secid= или ?ticker= → get_moex_info(...)
      - иначе список через get_moex_list(...), поддерживает ?engine=&market=&board=&search=&limit=
    """
    secid = (request.GET.get("secid") or "").strip()
    ticker = (request.GET.get("ticker") or "").strip()

    if secid or ticker:
        try:
            info = get_moex_info(secid=secid, ticker=ticker)
        except Exception as e:
            return JsonResponse({"error": f"moex_info failed: {e}"}, status=500, json_dumps_params={"ensure_ascii": False})
        return JsonResponse(info, json_dumps_params={"ensure_ascii": False})

    engine = (request.GET.get("engine") or "").strip()
    market = (request.GET.get("market") or "").strip()
    board = (request.GET.get("board") or "").strip()
    search = (request.GET.get("search") or "").strip()
    limit_s = (request.GET.get("limit") or "").strip()

    try:
        limit = int(limit_s) if limit_s else 100
        limit = max(1, min(limit, 1000))
    except Exception:
        limit = 100

    try:
        result = get_moex_list(engine=engine, market=market, board=board, search=search, limit=limit)
    except Exception as e:
        return JsonResponse({"error": f"moex_list failed: {e}"}, status=500, json_dumps_params={"ensure_ascii": False})

    return JsonResponse(result, json_dumps_params={"ensure_ascii": False})


@require_GET
def api_moex_instrument_info(request):
    """
    Информация по инструменту MOEX по ?secid= или ?ticker= (прямой прокси на get_moex_info).
    """
    secid = (request.GET.get("secid") or "").strip()
    ticker = (request.GET.get("ticker") or "").strip()

    if not secid and not ticker:
        return JsonResponse(
            {"error": "Either 'secid' or 'ticker' must be provided"},
            status=400,
            json_dumps_params={"ensure_ascii": False},
        )

    try:
        info = get_moex_info(secid=secid, ticker=ticker)
    except Exception as e:
        return JsonResponse({"error": f"moex_info failed: {e}"}, status=500, json_dumps_params={"ensure_ascii": False})

    return JsonResponse(info, json_dumps_params={"ensure_ascii": False})


@require_GET
def api_moex_options(request):
    """
    Эндпойнт для опционов MOEX (подключается в mm08/api_urls.py как moex/options/).
    Работает через сервисы mm08/services/moex_options.py:
      - get_options(...)  — получение списка опционов по фильтрам,
      - get_strikes(...)  — (опционально) получение доступных страйков.
    Если сервис отсутствует — вернём 501 с понятным сообщением.
    """
    if get_options is None:
        return JsonResponse(
            {"error": "moex_options service is not available (mm08/services/moex_options.py is missing)"},
            status=501,
            json_dumps_params={"ensure_ascii": False},
        )

    engine = (request.GET.get("engine") or "").strip()
    market = (request.GET.get("market") or "").strip()
    board = (request.GET.get("board") or "").strip()
    underlying = (request.GET.get("underlying") or request.GET.get("ticker") or "").strip()
    expiry = (request.GET.get("expiry") or request.GET.get("date") or "").strip()
    strike = (request.GET.get("strike") or "").strip()
    option_type = (request.GET.get("option_type") or "").strip()

    limit_s = (request.GET.get("limit") or "").strip()
    try:
        limit = int(limit_s) if limit_s else 200
        limit = max(1, min(limit, 2000))
    except Exception:
        limit = 200

    try:
        options = get_options(
            engine=engine,
            market=market,
            board=board,
            underlying=underlying,
            expiry=expiry,
            strike=strike,
            option_type=option_type,
            limit=limit,
        )
    except Exception as e:
        return JsonResponse({"error": f"get_options failed: {e}"}, status=500, json_dumps_params={"ensure_ascii": False})

    with_strikes = (request.GET.get("with_strikes") or "0").strip() in ("1", "true", "yes")
    strikes_data: Optional[Any] = None
    if with_strikes and get_strikes is not None:
        try:
            strikes_data = get_strikes(engine=engine, market=market, board=board, underlying=underlying, expiry=expiry)
        except Exception as e:
            strikes_data = {"error": f"get_strikes failed: {e}"}

    data: Dict[str, Any] = {
        "engine": engine,
        "market": market,
        "board": board,
        "underlying": underlying,
        "expiry": expiry,
        "count": len(options) if isinstance(options, list) else None,
        "options": options,
    }
    if with_strikes:
        data["strikes"] = strikes_data

    return JsonResponse(data, json_dumps_params={"ensure_ascii": False})
