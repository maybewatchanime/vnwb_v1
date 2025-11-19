# Установка XTLS-Reality-bot

## Автоматическая установка

```bash
# Скачиваем и запускаем скрипт автоустановки
wget https://raw.githubusercontent.com/PheeZz/XTLS-Reality-bot/main/autoinstall.sh
chmod +x autoinstall.sh
./autoinstall.sh
```

## Ручная установка

### 1. Установка зависимостей

```bash
# Python 3.11
sudo apt install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-dev python3.11-distutils python3.11-venv

# Poetry для управления зависимостями
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3.11 get-pip.py
pip3.11 install poetry

# PostgreSQL для базы данных
sudo apt install -y postgresql postgresql-contrib
```

### 2. Клонирование репозитория

```bash
git clone https://github.com/PheeZz/XTLS-Reality-bot.git
cd XTLS-Reality-bot
poetry install --no-root
```

### 3. Настройка базы данных

```bash
sudo -u postgres psql
CREATE DATABASE xtls_bot;
CREATE USER xtls_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE xtls_bot TO xtls_user;
\q
```

### 4. Конфигурация бота

```bash
nano source/data/.env
```

Заполните следующие параметры:

```env
# Токен телеграм бота (получите у @BotFather)
TG_BOT_TOKEN = "YOUR_BOT_TOKEN"

# Номер карты для платежей (если используете ручные платежи)
PAYMENT_CARD = "1234567890123456"

# Ваш Telegram ID (узнайте у @userinfobot)
ADMINS_IDS = "123456789"

# Префикс для конфигураций
CONFIGS_PREFIX = "MyVPN"

# Стоимость подписки
BASE_SUBSCRIPTION_MONTHLY_PRICE = "500₽"

# База данных
DB_NAME = "xtls_bot"
DB_USER = "xtls_user"
DB_USER_PASSWORD = "your_secure_password"
DB_HOST = "localhost"
DB_PORT = "5432"

# Путь к конфигурации Xray
XRAY_CONFIG_PATH = "/usr/local/etc/xray/config.json"

# Reality ключи (из вашей конфигурации Xray)
XRAY_PUBLICKEY = "YOUR_PUBLIC_KEY"
XRAY_SHORTID = "YOUR_SHORT_ID"
XRAY_SNI = "dl.google.com"

# Максимальное количество конфигов на пользователя
USER_DEFAULT_MAX_CONFIGS_COUNT = "2"
```

### 5. Создание таблиц в БД

```bash
$(poetry env info --executable) create_database_tables.py
```

### 6. Создание systemd сервиса

```bash
sudo nano /etc/systemd/system/xtls-bot.service
```

Добавьте:

```ini
[Unit]
Description=XTLS-Reality telegram bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/XTLS-Reality-bot/
ExecStart=/bin/bash -c 'cd /root/XTLS-Reality-bot/ && $(poetry env info --executable) app.py'
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

### 7. Запуск бота

```bash
sudo systemctl daemon-reload
sudo systemctl enable xtls-bot
sudo systemctl start xtls-bot
sudo systemctl status xtls-bot
```
