# MM/docker/gunicorn.conf.py
# ─────────────────────────────────────────────────────────────────────────────
# Назначение: конфигурация gunicorn для Django-проекта MM
# ─────────────────────────────────────────────────────────────────────────────

import multiprocessing  # модуль для определения числа CPU

bind = "unix:/run/gunicorn/gunicorn.sock"  # биндимся на unix-сокет для nginx
workers = int(__import__("os").getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))  # число воркеров
timeout = int(__import__("os").getenv("GUNICORN_TIMEOUT", "60"))  # таймаут воркера
accesslog = "-"  # лог запросов в stdout (перехватит supervisor)
errorlog = "-"   # лог ошибок в stdout
worker_class = "sync"  # обычный sync-воркер
