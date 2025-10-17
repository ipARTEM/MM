import pytest
from django.contrib.auth.models import Group, Permission
from django.urls import reverse

# Все тесты используют кастомную модель
@pytest.fixture
def UserModel(django_user_model):
    # django_user_model уже указывает на allusers.User
    return django_user_model

@pytest.fixture
def groups():
    """Возвращаем (analysts, managers) группы с нужными правами."""
    # Создаём/берём группы
    analysts, _ = Group.objects.get_or_create(name="Аналитики")
    managers, _ = Group.objects.get_or_create(name="Менеджеры")

    # Права на модель Instrument
    can_add = Permission.objects.get(codename="add_instrument")
    can_change = Permission.objects.get(codename="change_instrument")
    can_view = Permission.objects.get(codename="view_instrument")

    # Аналитики: только просмотр
    analysts.permissions.set([can_view])

    # Менеджеры: полный доступ к инструментам (минимально для тестов — add/change/view)
    managers.permissions.set([can_view, can_add, can_change])

    return analysts, managers

@pytest.fixture
def analyst(UserModel, groups):
    """Пользователь-аналитик (только просмотр)."""
    user = UserModel.objects.create_user(
        username="analyst",
        password="pass1234",
        role=UserModel.Role.ANALYST,
        email="a@example.com"
    )
    user.groups.add(groups[0])
    return user

@pytest.fixture
def manager(UserModel, groups):
    """Пользователь-менеджер (полный доступ)."""
    user = UserModel.objects.create_user(
        username="manager",
        password="pass1234",
        role=UserModel.Role.MANAGER,
        email="m@example.com"
    )
    user.groups.add(groups[1])
    return user

@pytest.fixture
def auth_client_analyst(client, analyst):
    """Клиент, залогиненный как аналитик."""
    client.force_login(analyst)
    return client

@pytest.fixture
def auth_client_manager(client, manager):
    """Клиент, залогиненный как менеджер."""
    client.force_login(manager)
    return client
