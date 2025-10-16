# allusers/apps.py
from django.apps import AppConfig
from django.db.models.signals import post_migrate


def setup_groups(sender, **kwargs):
    """
    Создаём/обновляем группы и права.
    Запускаем логику ТОЛЬКО когда отрабатывает post_migrate приложения mm08,
    т.к. именно тогда гарантированно созданы model-permissions для Candle/Instrument.
    """
    if sender.label != "mm08":
        return  # ждём, пока не мигрирует наше доменное приложение

    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType
    from django.apps import apps

    Instrument = apps.get_model("mm08", "Instrument")
    Candle = apps.get_model("mm08", "Candle")

    inst_ct = ContentType.objects.get_for_model(Instrument)
    candle_ct = ContentType.objects.get_for_model(Candle)

    # группы
    managers, _ = Group.objects.get_or_create(name="managers")
    analysts, _ = Group.objects.get_or_create(name="analysts")

    # стандартные права на Instrument
    inst_perms = list(Permission.objects.filter(content_type=inst_ct))
    # просмотр свечей
    view_candle = Permission.objects.get(content_type=candle_ct, codename="view_candle")

    # менеджеры: полный доступ к Instrument + просмотр Candle
    managers.permissions.set(inst_perms + [view_candle])

    # аналитики: только просмотр Instrument и Candle
    analysts.permissions.set(
        Permission.objects.filter(
            content_type__in=[inst_ct, candle_ct],
            codename__in=["view_instrument", "view_candle"],
        )
    )


class AllusersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "allusers"
    verbose_name = "Пользователи"

    def ready(self):
        # Подписываемся без sender, а внутри фильтруем по sender.label == "mm08"
        post_migrate.connect(setup_groups)
