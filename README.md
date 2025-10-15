# MM08 — Django MOEX Parser

Небольшой Django-проект для загрузки свечей с MOEX ISS API в БД и просмотра через админку, страницы и REST API.  
Основан на идеях из [FlaskParserMOEX](https://github.com/ipARTEM/FlaskParserMOEX).

## Стек
- Python 3.13
- Django 5.2
- SQLite (по умолчанию) / любая совместимая БД
- `requests` (для ISS API)
- DRF (для REST API)

## Быстрый старт (Windows / PowerShell)

```ps1
# 1) Клонирование и окружение
git clone <repo-url> MM
cd MM
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) Зависимости
pip install -r requirements.txt
# (или минимум) pip install django==5.2.7 djangorestframework requests python-dotenv

# 3) Настройки (создайте .env в корне)
# .env:
# KEY_DJ=ваш_секретный_ключ

# 4) Миграции и суперпользователь
python manage.py migrate
python manage.py createsuperuser

# 5) Запуск
python manage.py runserver 0.0.0.0:8088



👨‍💻 Автор  Artem Khimin

📝 Лицензия

Этот проект распространяется под лицензией MIT License.
© 2025 Artem Khimin