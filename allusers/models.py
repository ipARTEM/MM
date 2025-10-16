# Расширяем стандартного пользователя: добавляем роль и отображаемое имя.
from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        MANAGER = "manager", "Менеджер (полный доступ)"
        ANALYST = "analyst", "Аналитик (просмотр)"

    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.ANALYST,
        help_text="Роль влияет на набор прав по умолчанию."
    )
    display_name = models.CharField(max_length=100, blank=True, default="")

    def __str__(self) -> str:
        # В админке и шаблонах покажем понятное имя (если задано)
        return self.display_name or self.username

    @property
    def is_manager(self) -> bool:
        return self.role == self.Role.MANAGER

    @property
    def is_analyst(self) -> bool:
        return self.role == self.Role.ANALYST
