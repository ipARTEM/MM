import pytest
from django.urls import reverse

@pytest.mark.django_db
def test_login_page_accessible(client):
    r = client.get(reverse("allusers:login"))
    assert r.status_code == 200
    assert b"Вход" in r.content or b"Войти" in r.content

@pytest.mark.django_db
def test_profile_requires_login(client, auth_client_analyst):
    url = reverse("allusers:profile")

    # аноним — редирект на логин
    r1 = client.get(url)
    assert r1.status_code in (302, 301)
    assert "login" in r1["Location"]

    # залогинен — 200
    r2 = auth_client_analyst.get(url)
    assert r2.status_code == 200
    assert b"Профиль" in r2.content
