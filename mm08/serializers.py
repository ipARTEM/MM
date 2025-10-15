from rest_framework import serializers
from .models import Instrument, Candle


class InstrumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Instrument
        fields = ["id", "ticker", "secid", "shortname", "engine", "market", "board", "lot_size", "is_active"]


class CandleSerializer(serializers.ModelSerializer):
    instrument = serializers.SlugRelatedField(slug_field="ticker", read_only=True)

    class Meta:
        model = Candle
        fields = ["instrument", "dt", "interval", "open", "high", "low", "close", "volume"]
