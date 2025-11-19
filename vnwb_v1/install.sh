#!/bin/bash

# VPN Telegram Bot - Автоматическая установка
# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=================================${NC}"
echo -e "${GREEN}  VPN Telegram Bot Installer     ${NC}"
echo -e "${GREEN}=================================${NC}"
echo ""

# Проверка root прав
if [[ $EUID -eq 0 ]]; then
   echo -e "${RED}Этот скрипт не должен запускаться от root!${NC}"
   exit 1
fi

# Определение пользователя и домашней директории
CURRENT_USER=$(whoami)
HOME_DIR=$HOME
BOT_DIR="$HOME_DIR/vpn_bot"

echo -e "${YELLOW}Установка будет произведена для пользователя: $CURRENT_USER${NC}"
echo -e "${YELLOW}Директория установки: $BOT_DIR${NC}"
echo ""

# Функция для чтения ввода
read_input() {
    local prompt="$1"
    local variable_name="$2"
    local is_secret="$3"
    
    if [[ "$is_secret" == "true" ]]; then
        read -s -p "$prompt" value
        echo ""
    else
        read -p "$prompt" value
    fi
    
    eval "$variable_name='$value'"
}

# Сбор необходимых данных
echo -e "${GREEN}Шаг 1: Сбор информации${NC}"
echo "------------------------"

read_input "Введите токен бота от @BotFather: " BOT_TOKEN false
read_input "Введите ваш Telegram ID (узнать у @userinfobot): " ADMIN_ID false
read_input "Введите номер карты для приема платежей: " PAYMENT_CARD false
read_input "Введите домен вашего VPN сервера (например: vpn.example.com): " SERVER_DOMAIN false
read_input "Введите IP адрес вашего VPS: " SERVER_IP false

echo ""
echo -e "${GREEN}Шаг 2: Обновление системы${NC}"
echo "------------------------"
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git

echo ""
echo -e "${GREEN}Шаг 3: Создание директории и виртуального окружения${NC}"
echo "------------------------"
mkdir -p "$BOT_DIR"
cd "$BOT_DIR"

# Создаем виртуальное окружение
python3 -m venv venv
source venv/bin/activate

echo ""
echo -e "${GREEN}Шаг 4: Установка зависимостей${NC}"
echo "------------------------"

# Создаем requirements.txt если его нет
if [ ! -f "requirements.txt" ]; then
    cat > requirements.txt << 'EOF'
aiogram>=3.0.0
aiofiles>=23.0.0
sqlalchemy>=2.0.0
qrcode>=7.4.0
pillow>=10.0.0
python-dotenv>=1.0.0
EOF
fi

pip install -r requirements.txt

echo ""
echo -e "${GREEN}Шаг 5: Создание конфигурации${NC}"
echo "------------------------"

# Создаем .env файл
cat > .env << EOF
# Telegram Bot Configuration
BOT_TOKEN=$BOT_TOKEN
ADMIN_IDS=$ADMIN_ID

# Payment Settings  
PAYMENT_CARD=$PAYMENT_CARD

# Server Settings
SERVER_IP=$SERVER_IP
SERVER_DOMAIN=$SERVER_DOMAIN

# Xray Settings
XRAY_CONFIG_PATH=/usr/local/etc/xray/config.json
XRAY_SERVICE_NAME=xray
EOF

echo -e "${GREEN}Конфигурация создана${NC}"

echo ""
echo -e "${GREEN}Шаг 6: Настройка прав sudo для управления Xray${NC}"
echo "------------------------"

# Создаем временный файл для sudoers
SUDO_FILE="/tmp/vpn_bot_sudo"
cat > $SUDO_FILE << EOF
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart xray
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl status xray
EOF

echo -e "${YELLOW}Для продолжения потребуется ввести пароль sudo${NC}"
sudo cp $SUDO_FILE /etc/sudoers.d/vpn_bot
sudo chmod 440 /etc/sudoers.d/vpn_bot
rm $SUDO_FILE

echo ""
echo -e "${GREEN}Шаг 7: Создание systemd сервиса${NC}"
echo "------------------------"

# Создаем файл сервиса
sudo tee /etc/systemd/system/vpn_bot.service > /dev/null << EOF
[Unit]
Description=VPN Telegram Bot
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$BOT_DIR
Environment="PATH=$BOT_DIR/venv/bin"
ExecStart=$BOT_DIR/venv/bin/python $BOT_DIR/bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo ""
echo -e "${GREEN}Шаг 8: Проверка наличия файла bot.py${NC}"
echo "------------------------"

if [ ! -f "bot.py" ]; then
    echo -e "${YELLOW}Файл bot.py не найден!${NC}"
    echo -e "${YELLOW}Пожалуйста, скопируйте файл bot.py в директорию $BOT_DIR${NC}"
    echo -e "${YELLOW}После копирования выполните:${NC}"
    echo -e "${GREEN}sudo systemctl daemon-reload${NC}"
    echo -e "${GREEN}sudo systemctl enable vpn_bot${NC}"
    echo -e "${GREEN}sudo systemctl start vpn_bot${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}Шаг 9: Запуск бота${NC}"
echo "------------------------"

sudo systemctl daemon-reload
sudo systemctl enable vpn_bot
sudo systemctl start vpn_bot

sleep 3

# Проверка статуса
if sudo systemctl is-active --quiet vpn_bot; then
    echo -e "${GREEN}✅ Бот успешно запущен!${NC}"
else
    echo -e "${RED}❌ Ошибка запуска бота${NC}"
    echo -e "${YELLOW}Проверьте логи: sudo journalctl -u vpn_bot -n 50${NC}"
fi

echo ""
echo -e "${GREEN}=================================${NC}"
echo -e "${GREEN}     Установка завершена!        ${NC}"
echo -e "${GREEN}=================================${NC}"
echo ""
echo -e "${GREEN}Полезные команды:${NC}"
echo -e "  Статус бота:     ${YELLOW}sudo systemctl status vpn_bot${NC}"
echo -e "  Логи бота:       ${YELLOW}sudo journalctl -u vpn_bot -f${NC}"
echo -e "  Перезапуск:      ${YELLOW}sudo systemctl restart vpn_bot${NC}"
echo -e "  Остановка:       ${YELLOW}sudo systemctl stop vpn_bot${NC}"
echo ""
echo -e "${GREEN}Настройка бота в Telegram:${NC}"
echo -e "1. Откройте вашего бота в Telegram"
echo -e "2. Отправьте команду /start"
echo -e "3. Настройте команды через @BotFather"
echo ""
echo -e "${YELLOW}Важно: Не забудьте настроить команды бота через @BotFather!${NC}"
