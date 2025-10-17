from django.urls import reverse
from ._utils import html


def test_login_page(client):
    r = client.get(reverse("allusers:login"))
    assert r.status_code == 200
    page = html(r)
    assert ("Вход" in page) or ("Войти" in page)


def test_register_page(client):
    r = client.get(reverse("allusers:register"))
    assert r.status_code == 200
    page = html(r)
    assert "Регистрация" in page
