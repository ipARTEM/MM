# MM/allusers/urls.py
# ─────────────────────────────────────────────────────────────────────────────
# Путь и имя файла: MM/allusers/urls.py
# Назначение: URL-маршруты приложения allusers (включая токены API)
# ─────────────────────────────────────────────────────────────────────────────

from django.urls import path  # импорт path для маршрутов
from django.contrib.auth import views as auth_views  # стандартные представления логина/логаута
from .views import RegisterView, ProfileView  # регистрация и профиль
# ↓ добавляем наши API-вью для токенов
from .api_views import ObtainOrCreateTokenView, RotateTokenView  # создание/получение, ротация токенов

app_name = "allusers"

urlpatterns = [
    path("login/",  auth_views.LoginView.as_view(template_name="allusers/login.html"), name="login"),   # логин
    path("logout/", auth_views.LogoutView.as_view(next_page="mm08:home"), name="logout"),               # логаут
    path("register/", RegisterView.as_view(), name="register"),                                         # регистрация
    path("profile/",  ProfileView.as_view(),  name="profile"),                                          # профиль

    # === API токенов DRF ===
    path("api/token/", ObtainOrCreateTokenView.as_view(), name="api_token_obtain"),     # получить/создать токен
    path("api/token/rotate/", RotateTokenView.as_view(), name="api_token_rotate"),      # ротировать токен
]
