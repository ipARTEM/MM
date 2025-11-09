# MM/mm08/permissions.py
# ─────────────────────────────────────────────────────────────────────────────
# Путь и имя файла: MM/mm08/permissions.py
# Назначение: Кастомные пермишены DRF
# ─────────────────────────────────────────────────────────────────────────────

from rest_framework.permissions import BasePermission, SAFE_METHODS  # базовый класс и список «безопасных» HTTP-методов

class IsStaffOrReadOnly(BasePermission):
    """Разрешает чтение всем. Изменения — только для пользователей со статусом is_staff=True.
    
    Это безопасная политика для административных эндпоинтов:
    - GET/HEAD/OPTIONS доступны всем
    - POST/PUT/PATCH/DELETE — только staff
    """
    # метод has_permission — проверяет доступ на уровне вью/запроса
    def has_permission(self, request, view):
        # Разрешаем безопасные методы всем (GET/HEAD/OPTIONS)
        if request.method in SAFE_METHODS:
            return True
        # На небезопасные методы доступ только staff-пользователям
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
