# MM/mm08/tests/conftest.py
import pytest
from django.contrib.auth.models import Permission
from mixer.backend.django import mixer as _mixer
from allusers.models import User

@pytest.fixture(autouse=True)
def _db(db):
    """Автоматически включаем БД для всех тестов в этом пакете."""
    pass

@pytest.fixture
def mixer():
    """Удобный алиас, чтобы писать mixer.blend(...) в тестах."""
    return _mixer

@pytest.fixture
def analyst() -> User:
    u = User.objects.create_user(username="analyst", password="p", role=User.Role.ANALYST)
    return u

@pytest.fixture
def manager() -> User:
    u = User.objects.create_user(username="manager", password="p", role=User.Role.MANAGER)
    # подстраховка: даём право добавлять инструмент напрямую
    perm = Permission.objects.get(codename="add_instrument")
    u.user_permissions.add(perm)
    return u

@pytest.fixture
def logged_client(client, analyst):
    client.login(username="analyst", password="p")
    return client
