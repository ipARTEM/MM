from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import InstrumentViewSet, CandleViewSet

router = DefaultRouter()
router.register(r"instruments", InstrumentViewSet, basename="api-instruments")
router.register(r"candles", CandleViewSet, basename="api-candles")

urlpatterns = [
    path("", include(router.urls)),
]
