from django.core.management.base import BaseCommand, CommandError
from django.core.management import call_command
from django.db import transaction


class Command(BaseCommand):
    help = "Пакетная загрузка нескольких тикеров через вызовы load_moex"

    def add_arguments(self, parser):
        parser.add_argument("--tickers", required=True, help="Список через запятую: SBER,GAZP,GMKN")
        parser.add_argument("--from", dest="date_from", required=True)
        parser.add_argument("--to", dest="date_till", required=True)
        parser.add_argument("--interval", type=int, default=60)
        parser.add_argument("--engine", default="stock")
        parser.add_argument("--market", default="shares")
        parser.add_argument("--board", default="TQBR")

    @transaction.atomic
    def handle(self, *args, **opts):
        tickers = [t.strip().upper() for t in opts["tickers"].split(",") if t.strip()]
        if not tickers:
            raise CommandError("Не переданы тикеры")

        date_from = opts["date_from"]
        date_till = opts["date_till"]

        for t in tickers:
            self.stdout.write(self.style.NOTICE(f"==> {t}"))
            call_command(
                "load_moex",
                "--ticker", t,
                "--from", date_from,
                "--to", date_till,
                "--interval", str(opts["interval"]),
                "--engine", opts["engine"],
                "--market", opts["market"],
                "--board", opts["board"],
                "--shortname", t,
            )

        self.stdout.write(self.style.SUCCESS("Пакетная загрузка завершена ✅"))
