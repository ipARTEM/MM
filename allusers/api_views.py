# MM/allusers/api_views.py
# ─────────────────────────────────────────────────────────────────────────────
# Путь и имя файла: MM/allusers/api_views.py
# Назначение: API-вью для управления токенами DRF (создание/получение/ротация)
# ─────────────────────────────────────────────────────────────────────────────

from typing import Any, Dict  # подсказки типов

from django.contrib.auth import authenticate  # проверка логин/пароль
from rest_framework.views import APIView  # базовый API-класс
from rest_framework.response import Response  # ответ DRF
from rest_framework import status, permissions, authentication  # статусы, права, аутентификация
from rest_framework.authtoken.models import Token  # модель токена
from rest_framework.authtoken.serializers import AuthTokenSerializer  # стандартный сериализатор логина

class ObtainOrCreateTokenView(APIView):
    """Создать/получить токен по логин/паролю.
    
    Ожидает POST с полями:
      - username: str
      - password: str

    Возвращает:
      { "token": "<ключ>", "user_id": <id>, "username": "<имя>" }
    """
    authentication_classes = [authentication.SessionAuthentication]  # допускаем вызов из Browsable API
    permission_classes = [permissions.AllowAny]  # любой может попытаться залогиниться

    def post(self, request, *args, **kwargs):
        # валидируем вход через стандартный сериализатор DRF
        serializer = AuthTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]  # пользователь после успешной аутентификации

        token, _ = Token.objects.get_or_create(user=user)  # получаем/создаём токен
        # формируем ответ
        resp: Dict[str, Any] = {"token": token.key, "user_id": user.id, "username": user.username}
        return Response(resp, status=status.HTTP_200_OK)


class RotateTokenView(APIView):
    """Пересоздать (ротировать) токен для текущего аутентифицированного пользователя.
    
    Ожидает:
      - заголовок Authorization: Token <ключ> ИЛИ активную сессию (логин через сайт)

    Возвращает новый токен:
      { "token": "<новый ключ>" }
    """
    authentication_classes = [authentication.SessionAuthentication, authentication.TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]  # только для аутентифицированных

    def post(self, request, *args, **kwargs):
        # удаляем старый токен, создаём новый
        Token.objects.filter(user=request.user).delete()  # очищаем старые токены
        new_token = Token.objects.create(user=request.user)  # создаём новый
        return Response({"token": new_token.key}, status=status.HTTP_200_OK)
