#!/usr/bin/env bash                          
# MM\docker\entrypoint.sh                     # путь файла в проекте
# Единая точка входа контейнера:
#  1) готовим каталоги/права для Postgres 15
#  2) initdb при первом старте
#  3) поднимаем ВРЕМЕННЫЙ postgres и ждём готовность
#  4) создаём роль/БД через UNIX-сокет
#  5) обеспечиваем KEY_DJ (.env), выполняем миграции и collectstatic (ПОКА postgres работает)
#  6) по завершении — останавливаем ВРЕМЕННЫЙ postgres и запускаем supervisor (postgres+gunicorn+nginx)

set -e                                       # при любой ошибке — завершить скрипт

# ── ЖЁСТКИЕ пути для PostgreSQL 15 ───────────────────────────────────────────
PG_BIN="/usr/lib/postgresql/15/bin"          # каталог бинарников PG15
PG_INITDB="${PG_BIN}/initdb"                  # путь к initdb
PG_POSTGRES="${PG_BIN}/postgres"              # путь к postgres
PG_PSQL="/usr/bin/psql"                       # путь к psql

# ── Готовим каталоги и права (Windows fix) ───────────────────────────────────
rm -rf /var/lib/postgresql/data              # удаляем data, если создан root-ом
install -d -m 700 -o postgres -g postgres /var/lib/postgresql/data   # создаём data (700, владелец postgres)
install -d -m 775 -o postgres -g postgres /var/run/postgresql        # создаём runtime-каталог для сокетов

# ── 1) initdb если каталог пуст ──────────────────────────────────────────────
if [ -z "$(ls -A /var/lib/postgresql/data 2>/dev/null)" ]; then      # проверяем, что data пустой
  echo "[entrypoint] Init PostgreSQL 15 data dir..."                  # лог
  su -s /bin/bash postgres -c "${PG_INITDB} -D /var/lib/postgresql/data"     # инициализация кластера
  su -s /bin/bash postgres -c "echo \"host all all 127.0.0.1/32 md5\" >> /var/lib/postgresql/data/pg_hba.conf"  # TCP доступ md5
  su -s /bin/bash postgres -c "echo \"listen_addresses = '127.0.0.1'\" >> /var/lib/postgresql/data/postgresql.conf" # слушаем localhost
fi                                                                    # конец initdb

# ── 2) Старт ВРЕМЕННОГО postgres ────────────────────────────────────────────
echo "[entrypoint] Start PostgreSQL 15 for init..."                   # лог
su -s /bin/bash postgres -c "${PG_POSTGRES} -D /var/lib/postgresql/data" > /var/log/postgres_boot.log 2>&1 &  # старт в фоне
PG_PID=$!                                                             # сохраняем PID временного postgres

# ── 3) Ожидаем готовность порта 5432 ────────────────────────────────────────
echo "[entrypoint] Waiting for PostgreSQL on 127.0.0.1:5432 ..."      # лог ожидания
for i in {1..60}; do                                                  # максимум минута ожидания
  (echo > /dev/tcp/127.0.0.1/5432) >/dev/null 2>&1 && break || true   # проверяем доступность порта
  sleep 1                                                              # пауза 1 сек
done                                                                   # конец ожидания

# ── 4) Создаём роль и БД через UNIX-сокет (без пароля) ──────────────────────
echo "[entrypoint] Ensure DB and user exist..."                       # лог
su -s /bin/bash postgres -c \
"psql -Atqc \"SELECT 1 FROM pg_roles WHERE rolname='${POSTGRES_USER}'\" | grep -q 1 \
 || psql -c \"CREATE USER ${POSTGRES_USER} WITH ENCRYPTED PASSWORD '${POSTGRES_PASSWORD}';\""  # создать роль при отсутствии
su -s /bin/bash postgres -c \
"psql -Atqc \"SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'\" | grep -q 1 \
 || createdb -O ${POSTGRES_USER} ${POSTGRES_DB}"                                                # создать БД при отсутствии (владелец — наша роль)
su -s /bin/bash postgres -c \
"psql -d ${POSTGRES_DB} -c \"GRANT ALL PRIVILEGES ON DATABASE ${POSTGRES_DB} TO ${POSTGRES_USER};\""  # выдать права на всякий случай

# ── 5) KEY_DJ + миграции/статика (ПОКА postgres работает) ───────────────────
# 5.1 Генерируем KEY_DJ, если не задан; синхронизируем с /app/.env
if [ -z "${KEY_DJ:-}" ]; then                                        # если KEY_DJ не передан
  echo "[entrypoint] KEY_DJ is empty -> generating Django SECRET_KEY" # лог
  GEN_KEY=$(python - <<'PY'
from django.core.management.utils import get_random_secret_key
print(get_random_secret_key())
PY
)
  export KEY_DJ="${GEN_KEY}"                                         # экспортируем ключ в окружение процесса
  if [ -f /app/.env ]; then                                          # если .env уже есть — обновим/добавим KEY_DJ
    if grep -q '^KEY_DJ=' /app/.env ; then sed -i "s|^KEY_DJ=.*$|KEY_DJ=${KEY_DJ}|" /app/.env; else echo "KEY_DJ=${KEY_DJ}" >> /app/.env; fi
  else                                                                # если .env нет — создадим
    printf "KEY_DJ=%s\n" "${KEY_DJ}" > /app/.env                     # записываем ключ в .env
  fi
else                                                                  # если KEY_DJ пришёл из окружения
  if [ -f /app/.env ]; then                                          # синхронизируем с .env
    if grep -q '^KEY_DJ=' /app/.env ; then sed -i "s|^KEY_DJ=.*$|KEY_DJ=${KEY_DJ}|" /app/.env; else echo "KEY_DJ=${KEY_DJ}" >> /app/.env; fi
  else
    printf "KEY_DJ=%s\n" "${KEY_DJ}" > /app/.env
  fi
fi

# 5.2 Django: миграции и сбор статики (Postgres ещё работает)
echo "[entrypoint] Django migrate & collectstatic..."                # лог действий Django
export DB_ENGINE=postgresql                                          # движок БД
export POSTGRES_HOST=127.0.0.1                                       # хост БД (внутри контейнера)
export POSTGRES_PORT=5432                                            # порт БД
python manage.py migrate --noinput                                   # применяем миграции
python manage.py collectstatic --noinput                             # собираем статику

# 5.3 Создаём суперпользователя через Django-shell (надёжно для любых моделей)
if [ -n "${DJANGO_SUPERUSER_USERNAME}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD}" ]; then   # если заданы логин и пароль
  echo "[entrypoint] Ensure Django superuser exists..."              # лог
  python - <<'PY' || true                                            # при любой ошибке — не валим весь скрипт
import os                                                            # импорт os для чтения env
import django                                                        # импорт django для инициализации
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MM.settings")       # указываем модуль настроек
django.setup()                                                       # инициализация Django
from django.contrib.auth import get_user_model                       # функция получения модели пользователя
User = get_user_model()                                              # получаем модель
username = os.environ.get("DJANGO_SUPERUSER_USERNAME")               # имя суперюзера из env
email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "admin@example.com")# email суперюзера (дефолт)
password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")               # пароль суперюзера из env
if username and password:                                            # проверяем что и логин, и пароль заданы
    qs = User.objects.filter(**({User.USERNAME_FIELD: username}))    # ищем по USERNAME_FIELD модели
    if qs.exists():                                                  # если уже есть такой пользователь
        print(f"[entrypoint] Superuser '{username}' already exists") # пишем лог и ничего не делаем
    else:                                                            # иначе создаём суперпользователя
        User.objects.create_superuser(**({User.USERNAME_FIELD: username}), email=email, password=password)  # создаём суперюзера
        print(f"[entrypoint] Superuser '{username}' created")        # пишем лог об успешном создании
else:                                                                # если логин/пароль не заданы
    print("[entrypoint] Superuser env vars not provided -> skip")    # просто пропускаем создание
PY
fi                                                                    # конец блока суперпользователя

# ── 6) Останавливаем ВРЕМЕННЫЙ postgres и запускаем supervisor ──────────────
echo "[entrypoint] Stop bootstrap PostgreSQL..."                     # лог
kill ${PG_PID} || true                                               # мягко завершаем временный postgres
wait ${PG_PID} || true                                               # ждём выхода процесса

echo "[entrypoint] Start supervisord..."                             # лог
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf # supervisor как PID1 (postgres+gunicorn+nginx)
