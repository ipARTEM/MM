from django.urls import path, include
from . import views

app_name = "mm08"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),

    # Инструменты
    path("instruments/", views.InstrumentListView.as_view(), name="instrument_list"),
    path("instruments/new/", views.InstrumentCreateView.as_view(), name="instrument_create"),
    path("instruments/<str:ticker>/", views.InstrumentDetailView.as_view(), name="instrument_detail"),  # NEW

    # Свечи
    path("candles/filter/", views.CandleFilterView.as_view(), name="candle_filter"),
    path("candles/<str:ticker>/", views.CandleListView.as_view(), name="candle_list"),

    # Графики
    path("chart/<str:ticker>/", views.ChartView.as_view(), name="chart"),
    path("chart/<str:ticker>/data/", views.ChartDataView.as_view(), name="chart_data"),

    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),

    # API 
    path("api/", include("mm08.api_urls")),
]
