from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import InstrumentViewSet, CandleViewSet
from . import api_views

router = DefaultRouter()
router.register(r"instruments", InstrumentViewSet, basename="api-instruments")
router.register(r"candles", CandleViewSet, basename="api-candles")

urlpatterns = [
    path("moex/meta/",            api_views.api_moex_meta,            name="moex_meta"),
    path("moex/options/",         api_views.api_moex_options,         name="moex_options"),
    path("moex/instrument-info/", api_views.api_moex_instrument_info, name="moex_instrument_info"),
    path("", include(router.urls)),
]
