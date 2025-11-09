from django.urls import path, include
from . import views
from . import api_views

app_name = "mm08"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),

    # API 
    path("api/", include(("mm08.api_urls", "mm08_api"), namespace="mm08_api")),
    path("api-demo/", views.ApiDemoView.as_view(), name="api_demo"),  # демо-страница API  


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
    
    # Дашборд
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),

    # Теплокарты
    path("heatmaps/", views.HeatmapView.as_view(), name="heatmap"),
    path("heatmaps/snapshot/<int:pk>/", views.HeatmapView.as_view(), name="heatmap_by_pk"),
    path("heatmaps/refresh/", views.HeatmapRefreshView.as_view(), name="heatmap_refresh"),
    path("heatmaps/export.csv", views.HeatmapExportView.as_view(), name="heatmap_export"),

    path("heatmap/stocks/", views.StocksHeatmapView.as_view(), name="heatmap_stocks"),  # страница "Теплокарта Акции"


    path("moex/instrument-info/", api_views.api_moex_instrument_info, name="moex_instrument_info"),

    path("stocks/", views.StocksListView.as_view(), name="stocks_list"),
]

