from django.urls import path, include
from . import views

app_name = "mm08"

urlpatterns = [
    path("", views.home, name="home"),
    
    path("instruments/", views.instrument_list, name="instrument_list"),
    path("instruments/new/", views.instrument_create, name="instrument_create"),

    path("candles/filter/", views.candle_filter, name="candle_filter"),
    path("candles/<str:ticker>/", views.candle_list, name="candle_list"),

    path("chart/<str:ticker>/", views.chart, name="chart"),
    path("chart/<str:ticker>/data/", views.chart_data, name="chart_data"),

    path("dashboard/", views.dashboard, name="dashboard"),


    # API
    path("api/", include("mm08.api_urls")),
]
