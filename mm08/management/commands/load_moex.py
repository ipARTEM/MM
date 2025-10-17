import logging
from typing import Optional

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from mm08.models import Instrument
from mm08.services.moex_iss import MoexISSClient, InstrumentRowMapper

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Загрузка/обновление инструментов из ISS в модель Instrument (ticker=SECID)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--engine", type=str, default=None)
        parser.add_argument("--market", type=str, default=None)
        parser.add_argument("--board", type=str, default=None)
        parser.add_argument("--batch", type=int, default=100, help="Печать прогресса каждые N записей")

    @transaction.atomic
    def handle(self, *args, **opts):
        engine: Optional[str] = opts.get("engine")
        market: Optional[str] = opts.get("market")
        board: Optional[str] = opts.get("board")
        batch: int = int(opts.get("batch") or 100)

        # Клиент без пауз — чтобы не вис
        client = MoexISSClient(timeout=10, pause_sec=0.0)

        self.stdout.write(f"→ Загружаем {engine}/{market}/{board} ...")
        saved = 0
        skipped = 0
        saw_first_page = False

        for i, rec in enumerate(client.iter_securities(engine=engine, market=market, board=board), start=1):
            if not saw_first_page:
                self.stdout.write("  ✓ получили первую страницу от ISS")
                saw_first_page = True

            secid = (rec.get("SECID") or rec.get("secid") or "").strip().upper()
            if not secid:
                skipped += 1
                if i % batch == 0:
                    self.stdout.write(f"  ...прочитано {i}, сохранено {saved}, пропущено {skipped}")
                continue

            ticker = secid  # твой уникальный ключ — ticker
            defaults = InstrumentRowMapper.to_instrument_defaults(rec)
            Instrument.objects.update_or_create(ticker=ticker, defaults=defaults)
            saved += 1

            if i % batch == 0:
                self.stdout.write(f"  ...прочитано {i}, сохранено {saved}, пропущено {skipped}")

        if not saw_first_page:
            self.stdout.write(self.style.WARNING("! От ISS не пришло ни одной строки (проверь фильтры)"))

        msg = f"Готово: сохранено/обновлено {saved}, пропущено {skipped}."
        logger.info(msg)
        self.stdout.write(self.style.SUCCESS(msg))
