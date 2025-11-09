# MM/mm08/serializers.py
# ─────────────────────────────────────────────────────────────────────────────
# Путь и имя файла: MM/mm08/serializers.py
# Назначение: DRF-сериализаторы для моделей приложения mm08
# ─────────────────────────────────────────────────────────────────────────────

from typing import Any  # типы для подсказок
from rest_framework import serializers # импорт базового сериализатора
from .models import Instrument, Candle , HeatSnapshot, HeatTile  # импорт нужных моделей


class InstrumentSerializer(serializers.ModelSerializer):
    """Сериализатор инструмента: отдаёт ключевые поля по тикеру."""
    class Meta:  # мета-класс DRF  
        model = Instrument            # привязываем к модели  
        fields = ["id", "ticker", "secid", "shortname", "engine", "market", "board", "lot_size", "is_active"]  # поля API  


class CandleSerializer(serializers.ModelSerializer):
    """Сериализатор свечи: отдаём OHLCV и интервал."""
    instrument = serializers.SlugRelatedField(slug_field="ticker", read_only=True)  # читаем тикер из связанной модели  

    class Meta:
        model = Candle
        fields = ["instrument", "dt", "interval", "open", "high", "low", "close", "volume"]


class HeatTileSerializer(serializers.ModelSerializer):
    """Сериализатор плитки теплокарты (одна бумага в снапшоте)."""
    snapshot_id = serializers.IntegerField(source="snapshot.id", read_only=True)  # отдаём ID снапшота  

    class Meta:
        model = HeatTile
        fields = [
            "id",             # первичный ключ  
            "snapshot_id",    # ссылка на снапшот  
            "ticker",         # тикер бумаги  
            "shortname",      # короткое имя  
            "engine",         # движок  
            "market",         # рынок  
            "board",          # режим торгов  
            "last",           # последняя цена  
            "change_pct",     # изменение в %  
            # при необходимости можно добавить ещё поля, когда они появятся в модели  
        ]


class HeatSnapshotSerializer(serializers.ModelSerializer):
    """Сериализатор снимка теплокарты (без вложенных плиток по умолчанию)."""
    class Meta:
        model = HeatSnapshot
        fields = [
            "id",        # ID снапшота  
            "date",      # дата  
            "board",     # режим торгов  
            "label",     # метка (fast/fresh/close)  
            "source",    # источник (moex)  
            "created_at",# время создания (из базовой модели)  
            "updated_at",# время обновления (из базовой модели)  
        ]


class HeatSnapshotWithTilesSerializer(HeatSnapshotSerializer):
    """Сериализатор снапшота с вложенными плитками (для детального просмотра)."""
    tiles = HeatTileSerializer(many=True, read_only=True)  # добавляем вложенный список плиток  

    class Meta(HeatSnapshotSerializer.Meta):
        fields = HeatSnapshotSerializer.Meta.fields + ["tiles"]  # переиспользуем базовый список + 'tiles'  