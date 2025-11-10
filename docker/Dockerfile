# MM\docker\Dockerfile
# Назначение: единый образ с Python 3.11 + Nginx + Gunicorn + Supervisor + PostgreSQL 15 (жёстко)
# Важно: добавляем официальный репозиторий PGDG, потому что в Debian trixie пакеты postgresql-15 отсутствуют.

FROM python:3.11-slim                                   

ENV DEBIAN_FRONTEND=noninteractive                      

# --- Блок 1. Базовые утилиты (curl/gnupg/lsb-release нужны для подключения PGDG) ---
RUN apt-get update \                                    
 && apt-get install -y --no-install-recommends \        
      curl \                                            
      ca-certificates \                                 
      tzdata \                                          
      gnupg \                                           
      wget \                                            
      lsb-release \                                     
 && rm -rf /var/lib/apt/lists/*                         

# --- Блок 2. Подключаем официальный репозиторий PostgreSQL (PGDG) ---
RUN echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt $(. /etc/os-release; echo $VERSION_CODENAME)-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \             
 && wget -qO- https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor > /usr/share/keyrings/postgresql.gpg
                                                        # скачиваем и сохраняем gpg-ключ PGDG в keyring

# --- Блок 3. Ставим Nginx, Supervisor и ИМЕННО PostgreSQL 15 + client + contrib ---
RUN apt-get update \                                    
 && apt-get install -y --no-install-recommends \        
      nginx \                                           
      supervisor \                                      
      postgresql-15 \                                   
      postgresql-client-15 \                            
      postgresql-contrib-15 \                           
 && rm -rf /var/lib/apt/lists/*  

# --- Блок 4. Директория приложения ---
ENV APP_DIR=/app                                        
WORKDIR ${APP_DIR}                                      

# --- Блок 5. Python-зависимости (requirements.txt в UTF-16LE — конвертируем в UTF-8) ---
COPY requirements.txt /tmp/requirements.txt             
RUN iconv -f UTF-16LE -t UTF-8 /tmp/requirements.txt > /tmp/requirements.utf8.txt \  
                                                        # конвертируем файл зависимостей в UTF-8
 && pip install --no-cache-dir -r /tmp/requirements.utf8.txt \ 
                                                        # устанавливаем зависимости проекта
 && pip install --no-cache-dir gunicorn psycopg2-binary # докидываем gunicorn и драйвер к Postgres

# --- Блок 6. Копируем проект внутрь образа ---
COPY . ${APP_DIR}                                       

# --- Блок 7. Создаём каталоги для сокета gunicorn, логов и данных Postgres ---
RUN mkdir -p /run/gunicorn \                            
 && mkdir -p /var/log/supervisor \                     
 && mkdir -p /var/log/nginx \                           
 && mkdir -p /var/lib/postgresql/data \                 
 && mkdir -p ${APP_DIR}/staticfiles ${APP_DIR}/media    

# --- Блок 8. Конфиги Nginx/Gunicorn/Supervisor/Entrypoint ---
COPY docker/nginx/mm.conf /etc/nginx/sites-available/mm.conf                 
RUN ln -sf /etc/nginx/sites-available/mm.conf /etc/nginx/sites-enabled/mm.conf \  
                                                        # активируем сайт
 && rm -f /etc/nginx/sites-enabled/default              

COPY docker/gunicorn.conf.py /etc/gunicorn.conf.py      
COPY docker/supervisord.conf /etc/supervisor/conf.d/supervisord.conf  
COPY docker/entrypoint.sh /entrypoint.sh                

RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh               # гарантируем LF-окончания и +x для entrypoint

# --- Блок 9. Значения по умолчанию для переменных окружения (можно переопределить в docker run) ---
ENV DJANGO_SETTINGS_MODULE=MM.settings \                
    DB_ENGINE=postgresql \                              
    POSTGRES_DB=mm_db \                                 
    POSTGRES_USER=mm_user \                             
    POSTGRES_PASSWORD=mm_pass \                         
    POSTGRES_HOST=127.0.0.1 \                           
    POSTGRES_PORT=5432 \                                
    ALLOWED_HOSTS=localhost,127.0.0.1 \                 
    MEDIA_ROOT=/app/media \                             
    GUNICORN_WORKERS=3 \                                
    GUNICORN_TIMEOUT=60                                 

EXPOSE 80                                               
CMD ["/entrypoint.sh"]                                  