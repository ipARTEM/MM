# MM/mm08/api_urls.py
# ─────────────────────────────────────────────────────────────────────────────
# Путь и имя файла: MM/mm08/api_urls.py
# Назначение: маршруты DRF (router) и дополнительные ручки API
# ─────────────────────────────────────────────────────────────────────────────

from django.urls import path, include                           # функции маршрутизации  
from rest_framework.routers import DefaultRouter                # роутер DRF  
from .api_views import InstrumentViewSet, CandleViewSet, HeatSnapshotViewSet, HeatTileViewSet  # импорт ViewSet’ов  
from . import api_views                                         # импорт функций API  

router = DefaultRouter()                                        # создаём роутер  
router.register(r"instruments", InstrumentViewSet, basename="api-instruments")  # инструменты  
router.register(r"candles", CandleViewSet, basename="api-candles")              # свечи  
router.register(r"heat/snapshots", HeatSnapshotViewSet, basename="api-heat-snapshots")  # снапшоты теплокарты  
router.register(r"heat/tiles", HeatTileViewSet, basename="api-heat-tiles")              # плитки теплокарты  

urlpatterns = [
    path("moex/meta/",            api_views.api_moex_meta,            name="moex_meta"),             # мета-инфо МОЕХ  
    path("moex/options/",         api_views.api_moex_options,         name="moex_options"),          # опционы МОЕХ  
    path("moex/instrument-info/", api_views.api_moex_instrument_info, name="moex_instrument_info"),  # инфо по инструменту  
    path("", include(router.urls)),  # подключаем все ViewSet’ы  
]