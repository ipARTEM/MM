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