# Project/mm08/services/heatmap.py
# Идемпотентная сборка снапшота теплокарты с upsert-поведением.

from __future__ import annotations

from decimal import Decimal
from typing import List, Tuple

from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from ..models import Instrument, Candle, HeatSnapshot, HeatTile


BULK_SIZE: int = 1000  # размер пачки для bulk_create


def _latest_candle_subqueries():
    """
    Подзапросы для последней свечи (dt, close, volume) по каждому инструменту.
    Возвращает кортеж (dt_subq, close_subq, volume_subq).
    """
    last_dt_sq = Candle.objects.filter(instrument=OuterRef("pk")).order_by("-dt").values("dt")[:1]
    last_close_sq = Candle.objects.filter(instrument=OuterRef("pk")).order_by("-dt").values("close")[:1]
    last_volume_sq = Candle.objects.filter(instrument=OuterRef("pk")).order_by("-dt").values("volume")[:1]
    return last_dt_sq, last_close_sq, last_volume_sq


def build_snapshot(board: str = "TQBR", label: str = "", replace: bool = True) -> Tuple[HeatSnapshot, bool]:
    """
    Собирает (или обновляет) снапшот теплокарты.

    Поведение:
      - Вычисляет сегодняшнюю дату (локальную) → это поле уникальности вместе с board+label.
      - get_or_create(date=today, board=board, label=label or "manual").
      - Если снапшот уже был и replace=True → удаляем старые плитки и создаём заново.
      - Возвращает (snapshot, created), где created=True, если снапшот только что создан.

    Параметры:
      board   : код доски, по умолчанию "TQBR"
      label   : метка снапшота; если пустая, используется "manual"
      replace : если False — при существующем снапшоте данные не перетираем, просто возвращаем его
    """
    label = label or "manual"
    today = timezone.localdate()  # важно: уникальность по ДАТЕ, не по datetime

    # Подготовим инструменты с аннотациями по последней свече
    last_dt_sq, last_close_sq, last_volume_sq = _latest_candle_subqueries()
    # делаем шире: берем всех инструментов указанной доски (без фильтра is_active),
# чтобы теплокарта всегда была «полной», даже если свечей в БД пока нет.
    instruments_qs = (
        Instrument.objects.filter(board=board)
        .only("id", "ticker", "shortname", "board")
        .annotate(
            _last_dt=Subquery(last_dt_sq),
            _last_close=Subquery(last_close_sq),
            _last_volume=Subquery(last_volume_sq),
        )
        .order_by("ticker")
    )

    instruments: List[Instrument] = list(instruments_qs)

    with transaction.atomic():
        # Ищем или создаём снапшот. created=True → впервые за сегодня.
        snapshot, created = HeatSnapshot.objects.get_or_create(
            date=today,
            board=board,
            label=label,
            defaults={
                # на случай, если в модели есть created_at (не критично, если auto_now_add)
                "created_at": timezone.now(),
            },
        )

        if (not created) and (not replace):
            # Идемпотентный режим без перезаписи — просто вернуть существующий
            return snapshot, False

        # Если снапшот существовал и replace=True — очищаем старые плитки
        if not created:
            HeatTile.objects.filter(snapshot=snapshot).delete()

        # Сформируем новые плитки
        new_tiles: List[HeatTile] = []
        for inst in instruments:
            last = inst.__dict__.get("_last_close") or Decimal("0")
            volume = inst.__dict__.get("_last_volume") or 0

            try:
                turnover = (Decimal(str(last)) * Decimal(str(volume))) if last is not None else Decimal("0")
            except Exception:
                turnover = Decimal("0")

            new_tiles.append(
                HeatTile(
                    snapshot=snapshot,
                    ticker=inst.ticker,
                    shortname=getattr(inst, "shortname", "") or inst.ticker,
                    last=last or Decimal("0"),
                    change_pct=Decimal("0"),  # упрощённо; можно рассчитать от предыдущей свечи
                    turnover=turnover,
                    volume=volume or 0,
                )
            )

        # Вставляем пачками
        for i in range(0, len(new_tiles), BULK_SIZE):
            HeatTile.objects.bulk_create(new_tiles[i : i + BULK_SIZE], batch_size=BULK_SIZE)

    return snapshot, created
