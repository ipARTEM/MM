from django.urls import path, include
from . import views

app_name = "mm08"

urlpatterns = [
    # path('', views.index, name='index'),
    path("", views.home, name="home"),
    path("instruments/", views.instrument_list, name="instrument_list"),
    path("candles/<str:ticker>/", views.candle_list, name="candle_list"),

    # Роуты для графиков
    path("chart/<str:ticker>/", views.chart, name="chart"),
    path("chart/<str:ticker>/data/", views.chart_data, name="chart_data"),


    # API
    path("api/", include("mm08.api_urls")),
]
