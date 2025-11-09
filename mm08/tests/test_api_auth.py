# MM/tests/test_api_auth.py
# ─────────────────────────────────────────────────────────────────────────────
# Путь и имя файла: MM/tests/test_api_auth.py
# Назначение: Простые проверки токен-логина и доступа к API
# ─────────────────────────────────────────────────────────────────────────────

import pytest  # фреймворк тестирования
from django.contrib.auth import get_user_model  # модель пользователя
from rest_framework.test import APIClient  # тест-клиент DRF

User = get_user_model()  # получаем кастомную/стандартную модель пользователя

@pytest.mark.django_db
def test_obtain_token_and_access_public_api():
    # создаём пользователя
    user = User.objects.create_user(username="user1", password="pass12345")  # тестовый пользователь

    # берём токен
    client = APIClient()  # создаём DRF-клиент
    resp = client.post("/users/api/token/", {"username": "user1", "password": "pass12345"}, format="json")
    assert resp.status_code == 200  # должен вернуться 200
    token = resp.json()["token"]    # извлекаем ключ токена

    # доступ к публичному read-only эндпоинту без токена (должен пускать)
    resp_public = client.get("/api/instruments/")  # пример — список инструментов (подставь реальный URL, если другой)
    assert resp_public.status_code == 200  # публично доступен на чтение

    # доступ с токеном — тоже ОК
    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")  # выставляем заголовок авторизации
    resp_auth = client.get("/api/instruments/")
    assert resp_auth.status_code == 200  # должен пускать

@pytest.mark.django_db
def test_rotate_token_requires_auth():
    user = User.objects.create_user(username="user2", password="pass12345")  # второй пользователь

    client = APIClient()  # клиент без авторизации
    # попытка ротации без авторизации — запрет
    resp_forbidden = client.post("/users/api/token/rotate/", {}, format="json")
    assert resp_forbidden.status_code in (401, 403)

    # авторизуемся токеном и ротируем
    resp_token = client.post("/users/api/token/", {"username": "user2", "password": "pass12345"}, format="json")
    token = resp_token.json()["token"]
    client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
    resp_rotate = client.post("/users/api/token/rotate/", {}, format="json")
    assert resp_rotate.status_code == 200  # должен вернуть новый токен
    assert "token" in resp_rotate.json()   # проверяем поле токена
