# MM/MM/urls.py
# ─────────────────────────────────────────────────────────────────────────────
# Путь и имя файла: MM/MM/urls.py
# Назначение: корневые URL-маршруты проекта + безопасное подключение debug_toolbar
# ─────────────────────────────────────────────────────────────────────────────

from django.contrib import admin            # админка Django
from django.urls import path, include       # функции для описания маршрутов
from django.conf import settings            # доступ к settings для проверки DEBUG
from django.conf.urls.static import static       # helper для медиа-URL

urlpatterns = [
    path("admin/", admin.site.urls),                       # маршрут в админку
    path("allusers/", include("allusers.urls")),           # маршруты приложения авторизации
    path("", include(("mm08.urls", "mm08"), namespace="mm08")),  # маршруты основного приложения
]

# Подключаем URL-ы тулбара только если включён DEBUG и тулбар активирован
if settings.DEBUG and getattr(settings, "ENABLE_DEBUG_TOOLBAR", True):
    import debug_toolbar  # импортируем пакет только при необходимости
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Назначаем кастомный обработчик 403 (дублируем настройку как в settings)
handler403 = "mm08.views.custom_permission_denied"
