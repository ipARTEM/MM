# MM/MM/settings.py
# ─────────────────────────────────────────────────────────────────────────────
# Путь и имя файла: MM/MM/settings.py
# Назначение: глобальные настройки проекта Django + безопасная интеграция django-debug-toolbar
# Принципы: сохраняем существующие переменные, добавляем тулбар только при DEBUG,
# ─────────────────────────────────────────────────────────────────────────────

from pathlib import Path  # стандартный модуль для работы с путями (Path-объект)
import os                 # модуль для чтения переменных окружения и работы с ОС
import socket             # модуль нужен для вычисления INTERNAL_IPS (Docker/WSL кейсы)
from dotenv import load_dotenv  # загрузка значений из .env
from django.conf.urls import handler403  # импортируем ссылку на обработчик 403 для назначения

# Назначаем кастомный обработчик 403 на функцию из нашего приложения mm08
handler403 = "mm08.views.custom_permission_denied"

# BASE_DIR — корень проекта (папка MM). Используем для формирования других путей.
BASE_DIR = Path(__file__).resolve().parent.parent

# ── Быстрая стартовая секция (важное для безопасности) ───────────────────────

# Подгружаем файл окружения .env, расположенный в корне проекта
load_dotenv(BASE_DIR / ".env")

# Секретный ключ берём из переменной окружения KEY_DJ
SECRET_KEY = os.getenv("KEY_DJ")

# Если ключ не найден, сразу падаем с понятной ошибкой — без него запуск небезопасен
if not SECRET_KEY:
    raise ValueError("❌ SECRET_KEY не найден в .env! Установите KEY_DJ.")

# Флаг режима разработки. В продакшене должен быть False.
DEBUG = True  # Вы указали, что сейчас работаете в Dev — оставляю True.

# Список разрешённых хостов. В Dev можно оставить пустым, в проде — обязательно заполнить.
ALLOWED_HOSTS: list[str] = []

# ── Приложения проекта ───────────────────────────────────────────────────────

INSTALLED_APPS = [
    "django.contrib.admin",            # админка Django
    "django.contrib.auth",             # система аутентификации
    "django.contrib.contenttypes",     # контент-тайпы (связаны с моделями)
    "django.contrib.sessions",         # сессии
    "django.contrib.messages",         # сообщения (flash-сообщения)
    "django.contrib.staticfiles",      # работа со статикой
    "rest_framework",                  # DRF — API фреймворк
    "allusers",                        # приложение с кастомной моделью пользователя
    "mm08",                            # основное приложение интерфейса
     "django_cleanup.apps.CleanupConfig", # django-cleanup (удаление файлов)
    # "debug_toolbar" — подключим ниже условно, чтобы в проде не торчал
]

# Опциональный флажок для быстрой деактивации тулбара даже при DEBUG=True
ENABLE_DEBUG_TOOLBAR = os.getenv("ENABLE_DEBUG_TOOLBAR", "1") == "1"

# Подключим debug_toolbar только в режиме разработки и если не отключён переменной
if DEBUG and ENABLE_DEBUG_TOOLBAR:
    INSTALLED_APPS += ["debug_toolbar"]  # добавляем приложение тулбара

# ── Middleware ───────────────────────────────────────────────────────────────

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",        # базовая безопасность
    "django.contrib.sessions.middleware.SessionMiddleware", # поддержка сессий
    "django.middleware.common.CommonMiddleware",            # общие улучшения (ETag и пр.)
    "django.middleware.csrf.CsrfViewMiddleware",            # защита от CSRF
    "django.contrib.auth.middleware.AuthenticationMiddleware",  # аутентификация пользователя
    "django.contrib.messages.middleware.MessageMiddleware",     # флеш-сообщения
    "django.middleware.clickjacking.XFrameOptionsMiddleware",   # защита от clickjacking
]

# Если тулбар включён — вставляем его middleware сразу после SecurityMiddleware
if DEBUG and ENABLE_DEBUG_TOOLBAR:
    _dt_mw = "debug_toolbar.middleware.DebugToolbarMiddleware"  # название middleware тулбара
    try:
        # Ищем индекс SecurityMiddleware, чтобы вставить следом (рекомендация Django)
        sec_idx = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware")
        if _dt_mw not in MIDDLEWARE:
            MIDDLEWARE.insert(sec_idx + 1, _dt_mw)  # вставляем на нужную позицию
    except ValueError:
        # Если по какой-то причине SecurityMiddleware не нашли — добавим в начало
        if _dt_mw not in MIDDLEWARE:
            MIDDLEWARE = [_dt_mw] + MIDDLEWARE

# ── Пользовательская модель пользователя и redirect’ы ────────────────────────

AUTH_USER_MODEL = "allusers.User"     # указываем кастомную модель пользователя

LOGIN_URL = "allusers:login"          # страница логина
LOGIN_REDIRECT_URL = "mm08:home"      # куда отправлять после логина
LOGOUT_REDIRECT_URL = "mm08:home"     # куда отправлять после логаута

# ── Урлы и WSGI ──────────────────────────────────────────────────────────────

ROOT_URLCONF = "MM.urls"              # корневой файл с маршрутами

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",  # бэкенд движка шаблонов
        "DIRS": [BASE_DIR / "templates"],  # дополнительная папка с шаблонами проекта
        "APP_DIRS": True,                  # включаем поиск шаблонов в приложениях
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",  # добавляет request в контекст
                "django.contrib.auth.context_processors.auth", # добавляет user/permissions
                "django.contrib.messages.context_processors.messages",  # для messages
            ],
        },
    },
]

WSGI_APPLICATION = "MM.wsgi.application"  # точка входа WSGI-сервера

# ── База данных ──────────────────────────────────────────────────────────────
# Сейчас SQLite для разработки; в проде переключитесь на PostgreSQL.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",    # движок БД
        "NAME": BASE_DIR / "db.sqlite3",           # путь до файла SQLite
    }
}

# ── Валидаторы паролей ──────────────────────────────────────────────────────

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},  # проверка на похожесть
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},            # минимальная длина
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},           # запрет частых паролей
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},          # запрет чисто цифровых
]

# ── Локализация и часовой пояс ──────────────────────────────────────────────

LANGUAGE_CODE = "ru-ru"       # язык интерфейса
TIME_ZONE = "Europe/Moscow"   # часовой пояс проекта
USE_I18N = True               # поддержка интернационализации
USE_TZ = True                 # хранить даты/время в БД в UTC (рекомендовано)

# ── Статика ─────────────────────────────────────────────────────────────────

STATIC_URL = "static/"                 # URL-префикс для статики
STATICFILES_DIRS = [BASE_DIR / "static"]  # папка со статикой проекта

# ── Первичный ключ по умолчанию ─────────────────────────────────────────────

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"  # тип авто-поля id

# ── DRF: базовые безопасные настройки ────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",  # JSON рендерер
        # При необходимости можно добавить Browsable API:
        "rest_framework.renderers.BrowsableAPIRenderer",  # удобно при разработке
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",  # стандартная пагинация
    "PAGE_SIZE": 50,  # дефолтный размер страницы (без «магических чисел» — можно вынести в .env при желании)
}

# ── Медиа (для будущих FileField/ImageField и работы django-cleanup) ─────────
# Ниже — безопасные дефолты: в dev файлы будут в папке проекта.
MEDIA_URL = "/media/"      # URL-префикс для медиа
MEDIA_ROOT = BASE_DIR / "media"  # директория хранения медиафайлов

# ── Django Debug Toolbar: INTERNAL_IPS и конфигурация ───────────────────────

if DEBUG and ENABLE_DEBUG_TOOLBAR:
    # INTERNAL_IPS определяет, с каких IP показывать тулбар.
    INTERNAL_IPS = ["127.0.0.1", "localhost", "::1"]  # базовые локальные значения

    # Дополнительная «магия» для Docker/WSL — вычисляем подсеть и подставляем *.1
    try:
        hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())  # получаем список IP
        INTERNAL_IPS += [ip[:-1] + "1" for ip in ips if "." in ip]        # 172.17.0.X -> 172.17.0.1
    except Exception:
        pass  # если не получилось — ничего страшного

    # Уберём дубликаты, сохраняя порядок
    INTERNAL_IPS = list(dict.fromkeys(INTERNAL_IPS))

    # Базовая конфигурация тулбара: всегда показываем и сворачиваем панели
    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda request: True,  # всегда показывать (удобно в Dev)
        "SHOW_COLLAPSED": True,                         # панели свёрнуты по умолчанию
        "HIDE_DJANGO_SQL": False,                       # не скрываем SQL-панель
        "RESULTS_CACHE_SIZE": 50,                       # кэш последних результатов
        'ROOT_TAG_EXTRA_ATTRS': 'style="z-index:9999"', # перекрыть фиксированные хедеры
    }

    # Набор панелей (можно править под себя)
    DEBUG_TOOLBAR_PANELS = [
        "debug_toolbar.panels.timer.TimerPanel",
        "debug_toolbar.panels.settings.SettingsPanel",
        "debug_toolbar.panels.headers.HeadersPanel",
        "debug_toolbar.panels.request.RequestPanel",
        "debug_toolbar.panels.sql.SQLPanel",
        "debug_toolbar.panels.templates.TemplatesPanel",
        "debug_toolbar.panels.staticfiles.StaticFilesPanel",
        "debug_toolbar.panels.cache.CachePanel",
        "debug_toolbar.panels.signals.SignalsPanel",
        "debug_toolbar.panels.logging.LoggingPanel",
        "debug_toolbar.panels.redirects.RedirectsPanel",
        "debug_toolbar.panels.profiling.ProfilingPanel",
    ]


# Оптимизация соединений БД: удерживаем коннект некоторое время (секунды)
try:
    DATABASES['default']['CONN_MAX_AGE'] = 60  # баланс между частотой запросов и переустановкой соединений
except Exception:
    pass