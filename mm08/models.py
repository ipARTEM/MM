from django.db import models


class Instrument(models.Model):
    """Биржевой инструмент (акция/фьючерс/ETF и т.д.)."""
    ticker = models.CharField(max_length=20, unique=True, db_index=True)   # SBER, GAZP, USDRUBF и т.п.
    secid = models.CharField(max_length=20, blank=True, default="")        # иногда совпадает с ticker
    shortname = models.CharField(max_length=100, blank=True, default="")
    engine = models.CharField(max_length=20, blank=True, default="stock")  # stock, futures и т.д.
    market = models.CharField(max_length=20, blank=True, default="shares") # shares, futures, index и т.п.
    board = models.CharField(max_length=20, blank=True, default="TQBR")    # TQBR, RFUD и т.д.
    lot_size = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Инструмент"
        verbose_name_plural = "Инструменты"

    def save(self, *args, **kwargs):
        # приведение к каноничному виду
        if self.ticker:
            self.ticker = self.ticker.strip().upper()   # убираем пробелы и делаем UPPER
        if self.secid:
            self.secid = self.secid.strip().upper()
        if self.board:
            self.board = self.board.strip().upper()
        if self.engine:
            self.engine = self.engine.strip().lower()
        if self.market:
            self.market = self.market.strip().lower()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.ticker


class Candle(models.Model):
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
    low = models.FloatField()
    close = models.FloatField()
    volume = models.BigIntegerField(default=0)

    class Meta:
        verbose_name = "Свеча"
        verbose_name_plural = "Свечи"
        unique_together = (("instrument", "dt", "interval"),)
        indexes = [
            models.Index(fields=["instrument", "interval", "dt"]),
        ]

    def __str__(self) -> str:
        return f"{self.instrument.ticker} {self.dt} [{self.get_interval_display()}]"
