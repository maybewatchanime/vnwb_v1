#!bin/bash

# ===========================================
# VPN Bot Installation Script
# Скрипт установки и настройки VPN бота
# ===========================================

set -e  # Останавливаем при ошибках

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для вывода сообщений
log() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Проверка прав root
if [[ $EUID -ne 0 ]]; then
   error "Этот скрипт должен запускаться с правами root (используйте sudo)"
fi

clear
echo "============================================="
echo "     VPN Bot Installer для XTLS-Reality     "
echo "============================================="
echo ""

# Проверка наличия Xray
if ! systemctl is-active --quiet xray; then
    error "Xray не установлен или не запущен! Сначала настройте Xray по инструкции."
fi

# Запрашиваем данные у пользователя
read -p "Введите токен бота от @BotFather: " BOT_TOKEN
if [ -z "$BOT_TOKEN" ]; then
    error "Токен бота не может быть пустым!"
fi

read -p "Введите ваш Telegram ID (получите у @userinfobot): " ADMIN_ID
if [ -z "$ADMIN_ID" ]; then
    error "Telegram ID не может быть пустым!"
fi

read -p "Введите домен вашего сервера (например: vpn.example.com): " SERVER_DOMAIN
if [ -z "$SERVER_DOMAIN" ]; then
    error "Домен сервера не может быть пустым!"
fi

# Получаем IP сервера
SERVER_IP=$(curl -s ifconfig.me)
log "Определен IP сервера: $SERVER_IP"

read -p "Введите стоимость подписки в рублях (по умолчанию 500): " SUBSCRIPTION_PRICE
SUBSCRIPTION_PRICE=${SUBSCRIPTION_PRICE:-500}

read -p "Введите длительность пробного периода в днях (по умолчанию 3): " TRIAL_DAYS
TRIAL_DAYS=${TRIAL_DAYS:-3}

read -p "Введите номер карты для приема платежей: " PAYMENT_CARD

# Создаем директорию для бота
BOT_DIR="/home/universal/vpn_bot"
log "Создаем директорию $BOT_DIR..."
mkdir -p $BOT_DIR
mkdir -p $BOT_DIR/logs
mkdir -p $BOT_DIR/backups

# Устанавливаем Python и pip если их нет
log "Проверяем Python..."
if ! command -v python3 &> /dev/null; then
    log "Устанавливаем Python 3..."
    apt update
    apt install -y python3 python3-pip python3-venv
fi

# Создаем виртуальное окружение
log "Создаем виртуальное окружение Python..."
cd $BOT_DIR
python3 -m venv venv
source venv/bin/activate

# Копируем файлы бота
log "Копируем файлы бота..."
cp /home/claude/vpn_bot.py $BOT_DIR/bot.py
cp /home/claude/requirements.txt $BOT_DIR/requirements.txt

# Заменяем конфигурацию в файле бота
log "Настраиваем конфигурацию бота..."
sed -i "s|YOUR_BOT_TOKEN|$BOT_TOKEN|g" $BOT_DIR/bot.py
sed -i "s|123456789|$ADMIN_ID|g" $BOT_DIR/bot.py
sed -i "s|your.domain.com|$SERVER_DOMAIN|g" $BOT_DIR/bot.py
sed -i "s|100.200.300.400|$SERVER_IP|g" $BOT_DIR/bot.py
sed -i "s|SUBSCRIPTION_PRICE = 500|SUBSCRIPTION_PRICE = $SUBSCRIPTION_PRICE|g" $BOT_DIR/bot.py
sed -i "s|TRIAL_DAYS = 3|TRIAL_DAYS = $TRIAL_DAYS|g" $BOT_DIR/bot.py
sed -i "s|1234 5678 9012 3456|$PAYMENT_CARD|g" $BOT_DIR/bot.py

# Устанавливаем зависимости
log "Устанавливаем зависимости Python..."
pip install --upgrade pip
pip install -r requirements.txt

# Создаем файл конфигурации
log "Создаем файл конфигурации..."
cat > $BOT_DIR/config.json << EOF
{
    "bot_token": "$BOT_TOKEN",
    "admin_ids": [$ADMIN_ID],
    "server_domain": "$SERVER_DOMAIN",
    "server_ip": "$SERVER_IP",
    "server_port": 443,
    "subscription_price": $SUBSCRIPTION_PRICE,
    "trial_days": $TRIAL_DAYS,
    "payment_card": "$PAYMENT_CARD",
    "database_path": "$BOT_DIR/database.json",
    "logs_path": "$BOT_DIR/logs/bot.log",
    "xray_config_path": "/usr/local/etc/xray/config.json"
}
EOF

# Создаем systemd сервис
log "Создаем systemd сервис..."
cat > /etc/systemd/system/vpn-bot.service << EOF
[Unit]
Description=VPN Telegram Bot for XTLS-Reality
After=network.target xray.service
Requires=xray.service

[Service]
Type=simple
User=root
WorkingDirectory=$BOT_DIR
Environment="PATH=$BOT_DIR/venv/bin"
ExecStart=$BOT_DIR/venv/bin/python $BOT_DIR/bot.py
Restart=always
RestartSec=10

# Логирование
StandardOutput=append:$BOT_DIR/logs/bot.log
StandardError=append:$BOT_DIR/logs/bot.error.log

[Install]
WantedBy=multi-user.target
EOF

# Создаем скрипт для резервного копирования
log "Создаем скрипт резервного копирования..."
cat > $BOT_DIR/backup.sh << 'BACKUP'
#!/bin/bash
BACKUP_DIR="/home/universal/vpn_bot/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Создаем резервную копию базы данных
cp /home/universal/vpn_bot/database.json $BACKUP_DIR/database_$DATE.json

# Создаем резервную копию конфигурации Xray
cp /usr/local/etc/xray/config.json $BACKUP_DIR/xray_config_$DATE.json

# Удаляем старые резервные копии (старше 7 дней)
find $BACKUP_DIR -name "*.json" -mtime +7 -delete

echo "Backup completed: $DATE"
BACKUP

chmod +x $BOT_DIR/backup.sh

# Добавляем резервное копирование в cron
log "Настраиваем автоматическое резервное копирование..."
(crontab -l 2>/dev/null; echo "0 3 * * * $BOT_DIR/backup.sh") | crontab -

# Создаем скрипт управления ботом
log "Создаем скрипт управления..."
cat > /usr/local/bin/vpn-bot << 'MANAGER'
#!/bin/bash

case "$1" in
    start)
        echo "Starting VPN Bot..."
        systemctl start vpn-bot
        echo "VPN Bot started"
        ;;
    stop)
        echo "Stopping VPN Bot..."
        systemctl stop vpn-bot
        echo "VPN Bot stopped"
        ;;
    restart)
        echo "Restarting VPN Bot..."
        systemctl restart vpn-bot
        echo "VPN Bot restarted"
        ;;
    status)
        systemctl status vpn-bot
        ;;
    logs)
        tail -f /home/universal/vpn_bot/logs/bot.log
        ;;
    backup)
        /home/universal/vpn_bot/backup.sh
        ;;
    update)
        echo "Updating VPN Bot..."
        cd /home/universal/vpn_bot
        source venv/bin/activate
        pip install --upgrade -r requirements.txt
        systemctl restart vpn-bot
        echo "VPN Bot updated"
        ;;
    *)
        echo "Usage: vpn-bot {start|stop|restart|status|logs|backup|update}"
        exit 1
        ;;
esac
MANAGER

chmod +x /usr/local/bin/vpn-bot

# Даем права на управление Xray через sudo без пароля
log "Настраиваем права для управления Xray..."
echo "universal ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart xray" >> /etc/sudoers
echo "universal ALL=(ALL) NOPASSWD: /usr/bin/systemctl status xray" >> /etc/sudoers
echo "universal ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-active xray" >> /etc/sudoers

# Перезагружаем systemd и запускаем бота
log "Запускаем бота..."
systemctl daemon-reload
systemctl enable vpn-bot
systemctl start vpn-bot

# Проверяем статус
sleep 3
if systemctl is-active --quiet vpn-bot; then
    log "✅ Бот успешно установлен и запущен!"
else
    error "❌ Ошибка при запуске бота. Проверьте логи: vpn-bot logs"
fi

# Выводим информацию
echo ""
echo "============================================="
echo "         Установка завершена!                "
echo "============================================="
echo ""
echo "📱 Бот: @$(curl -s "https://api.telegram.org/bot$BOT_TOKEN/getMe" | grep -oP '"username":"[^"]*' | cut -d'"' -f4)"
echo "🔑 Токен: ${BOT_TOKEN:0:10}..."
echo "👤 Админ ID: $ADMIN_ID"
echo "🌐 Домен: $SERVER_DOMAIN"
echo "💰 Цена подписки: $SUBSCRIPTION_PRICE руб/мес"
echo "🎁 Пробный период: $TRIAL_DAYS дней"
echo ""
echo "📝 Команды управления:"
echo "  vpn-bot start   - Запустить бота"
echo "  vpn-bot stop    - Остановить бота"
echo "  vpn-bot restart - Перезапустить бота"
echo "  vpn-bot status  - Статус бота"
echo "  vpn-bot logs    - Просмотр логов"
echo "  vpn-bot backup  - Создать резервную копию"
echo "  vpn-bot update  - Обновить зависимости"
echo ""
echo "📂 Файлы бота:"
echo "  Директория: $BOT_DIR"
echo "  База данных: $BOT_DIR/database.json"
echo "  Логи: $BOT_DIR/logs/"
echo "  Резервные копии: $BOT_DIR/backups/"
echo ""
echo "✅ Теперь перейдите в Telegram и напишите /start вашему боту!"
echo ""
warning "⚠️ ВАЖНО: Сохраните эту информацию в безопасном месте!"
