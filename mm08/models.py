from django.db import models
from django.utils import timezone
from django.conf import settings


# --- БАЗА ДЛЯ ВСЕХ МОДЕЛЕЙ ---
class TimeStampedModel(models.Model):
    """Абстрактная база с датами создания/изменения."""
    created_at = models.DateTimeField(default=timezone.now, editable=False, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменено")

    class Meta:
        abstract = True


class Instrument(TimeStampedModel):   # ← наследуемся
    """Биржевой инструмент (акция/фьючерс/ETF и т.д.)."""
    ticker = models.CharField(max_length=20, unique=True, db_index=True)
    secid = models.CharField(max_length=20, blank=True, default="")
    shortname = models.CharField(max_length=100, blank=True, default="")
    engine = models.CharField(max_length=20, blank=True, default="stock")   # stock, futures…
    market = models.CharField(max_length=20, blank=True, default="shares")  # shares, futures…
    board  = models.CharField(max_length=20, blank=True, default="TQBR")    # TQBR, RFUD…
    lot_size = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Инструмент"
        verbose_name_plural = "Инструменты"
        ordering = ["ticker"]

    # нормализация — убираем пробелы и приводим к канонике
    def save(self, *args, **kwargs):
        if self.ticker:   self.ticker   = self.ticker.strip().upper()
        if self.secid:    self.secid    = self.secid.strip().upper()
        if self.board:    self.board    = self.board.strip().upper()
        if self.engine:   self.engine   = self.engine.strip().lower()
        if self.market:   self.market   = self.market.strip().lower()
        super().save(*args, **kwargs)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="instruments",
        verbose_name="Владелец"
    )

    def __str__(self) -> str:
        return self.ticker


class Candle(TimeStampedModel):       # ← наследуемся
    """Свечи для инструмента (универсально: минутки/часы/дни)."""

    class Interval(models.IntegerChoices):
        M1 = 1, "1 мин"
        M10 = 10, "10 мин"
        H1 = 60, "1 час"
        D1 = 24 * 60, "1 день"

    instrument = models.ForeignKey(Instrument, on_delete=models.CASCADE, related_name="candles")
    dt = models.DateTimeField(db_index=True)  # 'begin' из ISS
    interval = models.IntegerField(choices=Interval.choices, default=Interval.M1)

    open = models.FloatField()
    high = models.FloatField()
    low  = models.FloatField()
    close= models.FloatField()
    volume = models.BigIntegerField(default=0)

    class Meta:
        verbose_name = "Свеча"
        verbose_name_plural = "Свечи"
        unique_together = (("instrument", "dt", "interval"),)
        indexes = [models.Index(fields=["instrument", "interval", "dt"])]
        ordering = ["-dt"]

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="candles_created",
        verbose_name="Кем загружена"
    )

    def __str__(self) -> str:
        return f"{self.instrument.ticker} {self.dt} [{self.get_interval_display()}]"
    

# --- HEATMAP (теплокарта) ------------------------------------------------------
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator

class HeatSnapshot(TimeStampedModel):
    """Снапшот теплокарты на определённую дату/момент."""
    date = models.DateField(db_index=True)
    board = models.CharField(max_length=16, default="TQBR", db_index=True)
    label = models.CharField(max_length=32, blank=True, default="")  # например: fast / fresh / close
    source = models.CharField(max_length=32, default="moex")

    class Meta:
        verbose_name = "Снимок теплокарты"
        verbose_name_plural = "Снимки теплокарты"
        ordering = ["-date", "-created_at"]
        unique_together = (("date", "board", "label"),)

    def __str__(self):
        return f"{self.date} {self.board} {self.label}".strip()


class HeatTile(models.Model):
    """Плитка теплокарты (одна бумага)."""
    snapshot = models.ForeignKey(HeatSnapshot, on_delete=models.CASCADE, related_name="tiles")
    ticker = models.CharField(max_length=20, db_index=True)
    shortname = models.CharField(max_length=100, blank=True, default="")
    engine = models.CharField(max_length=20, default="stock")
    market = models.CharField(max_length=20, default="shares")
    board  = models.CharField(max_length=20, default="TQBR")

    last = models.DecimalField(max_digits=20, decimal_places=6, default=Decimal("0"))
    change_pct = models.DecimalField(
        max_digits=8,
        decimal_places=3,
        null=True,           # ← добавили
        blank=True,          # ← добавили
        default=None,        # ← изменили (было Decimal("0"))
        help_text="Изменение % относительно предыдущего закрытия (LASTCHANGEPRC)",
    )
    turnover = models.BigIntegerField(default=0)  # оборот, если будет
    volume   = models.BigIntegerField(default=0)  # кол-во, если будет
    lot_size = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Плитка теплокарты"
        verbose_name_plural = "Плитки теплокарты"
        indexes = [
            models.Index(fields=["snapshot", "ticker"]),
            models.Index(fields=["snapshot", "change_pct"]),
        ]
        ordering = ["-change_pct"]

    def __str__(self):
        return f"{self.ticker} {self.change_pct}%"

    # Бин для цвета (-5..+5)
    @property
    def color_bin(self) -> int:
        # если процента нет — считаем нейтральным (0)
        v = float(self.change_pct) if self.change_pct is not None else 0.0
        v = max(min(v, 10.0), -10.0)
        return int(round(v / 2.0))
