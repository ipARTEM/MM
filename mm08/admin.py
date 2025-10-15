from django.contrib import admin
from .models import Instrument, Candle


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    list_display = ("ticker", "shortname", "engine", "market", "board", "lot_size", "is_active")
    list_filter = ("engine", "market", "board", "is_active")
    search_fields = ("ticker", "secid", "shortname")


@admin.register(Candle)
class CandleAdmin(admin.ModelAdmin):
    list_display = ("instrument", "dt", "interval", "open", "high", "low", "close", "volume")
    list_filter = ("instrument", "interval")
    search_fields = ("instrument__ticker",)
    date_hierarchy = "dt"
