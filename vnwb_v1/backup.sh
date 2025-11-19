#!/bin/bash

# Скрипт резервного копирования базы данных VPN бота

# Настройки
BACKUP_DIR="/home/vpsadmin/vpn_bot/backups"
DB_FILE="/home/vpsadmin/vpn_bot/vpn_bot.db"
BOT_SERVICE="vpn_bot"
KEEP_DAYS=30  # Хранить бэкапы за последние 30 дней

# Цвета
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Создаем директорию для бэкапов если её нет
mkdir -p "$BACKUP_DIR"

# Функция создания бэкапа
create_backup() {
    echo -e "${GREEN}Создание резервной копии...${NC}"
    
    # Останавливаем бота для консистентности данных
    echo "Останавливаем бота..."
    sudo systemctl stop $BOT_SERVICE
    
    # Создаем бэкап с текущей датой
    BACKUP_FILE="$BACKUP_DIR/vpn_bot_$(date +%Y%m%d_%H%M%S).db"
    cp "$DB_FILE" "$BACKUP_FILE"
    
    # Сжимаем бэкап
    gzip "$BACKUP_FILE"
    
    # Запускаем бота обратно
    echo "Запускаем бота..."
    sudo systemctl start $BOT_SERVICE
    
    echo -e "${GREEN}✅ Бэкап создан: ${BACKUP_FILE}.gz${NC}"
    
    # Удаляем старые бэкапы
    echo "Удаление старых бэкапов (старше $KEEP_DAYS дней)..."
    find "$BACKUP_DIR" -name "vpn_bot_*.db.gz" -mtime +$KEEP_DAYS -delete
}

# Функция восстановления из бэкапа
restore_backup() {
    echo -e "${GREEN}Доступные бэкапы:${NC}"
    
    # Показываем список бэкапов
    BACKUPS=($(ls -1 "$BACKUP_DIR"/vpn_bot_*.db.gz 2>/dev/null))
    
    if [ ${#BACKUPS[@]} -eq 0 ]; then
        echo -e "${RED}Бэкапы не найдены!${NC}"
        exit 1
    fi
    
    for i in "${!BACKUPS[@]}"; do
        echo "$((i+1)). $(basename ${BACKUPS[$i]})"
    done
    
    # Выбор бэкапа
    read -p "Выберите номер бэкапа для восстановления: " choice
    
    if [ "$choice" -lt 1 ] || [ "$choice" -gt ${#BACKUPS[@]} ]; then
        echo -e "${RED}Неверный выбор!${NC}"
        exit 1
    fi
    
    SELECTED_BACKUP="${BACKUPS[$((choice-1))]}"
    
    echo -e "${GREEN}Восстановление из: $(basename $SELECTED_BACKUP)${NC}"
    read -p "Вы уверены? Текущая база будет заменена! (y/N): " confirm
    
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Отменено."
        exit 0
    fi
    
    # Останавливаем бота
    echo "Останавливаем бота..."
    sudo systemctl stop $BOT_SERVICE
    
    # Создаем резервную копию текущей базы
    echo "Создаем резервную копию текущей базы..."
    cp "$DB_FILE" "$DB_FILE.before_restore"
    
    # Восстанавливаем из бэкапа
    echo "Восстанавливаем базу..."
    gunzip -c "$SELECTED_BACKUP" > "$DB_FILE"
    
    # Запускаем бота
    echo "Запускаем бота..."
    sudo systemctl start $BOT_SERVICE
    
    echo -e "${GREEN}✅ База успешно восстановлена!${NC}"
}

# Функция экспорта данных в CSV
export_to_csv() {
    echo -e "${GREEN}Экспорт данных в CSV...${NC}"
    
    # Создаем директорию для экспорта
    EXPORT_DIR="$BACKUP_DIR/export_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$EXPORT_DIR"
    
    # Экспортируем пользователей
    sqlite3 -header -csv "$DB_FILE" "SELECT * FROM users;" > "$EXPORT_DIR/users.csv"
    
    # Экспортируем платежи
    sqlite3 -header -csv "$DB_FILE" "SELECT * FROM payments;" > "$EXPORT_DIR/payments.csv"
    
    echo -e "${GREEN}✅ Данные экспортированы в: $EXPORT_DIR${NC}"
}

# Функция показа статистики
show_stats() {
    echo -e "${GREEN}Статистика базы данных:${NC}"
    echo "------------------------"
    
    TOTAL_USERS=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM users;")
    ACTIVE_USERS=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM users WHERE is_active=1;")
    TOTAL_PAYMENTS=$(sqlite3 "$DB_FILE" "SELECT COUNT(*) FROM payments WHERE is_confirmed=1;")
    TOTAL_REVENUE=$(sqlite3 "$DB_FILE" "SELECT IFNULL(SUM(amount), 0) FROM payments WHERE is_confirmed=1;")
    
    echo "Всего пользователей: $TOTAL_USERS"
    echo "Активных подписок: $ACTIVE_USERS"
    echo "Подтвержденных платежей: $TOTAL_PAYMENTS"
    echo "Общий доход: $TOTAL_REVENUE ₽"
    echo ""
    
    echo "Размер базы данных: $(du -h "$DB_FILE" | cut -f1)"
    echo "Количество бэкапов: $(ls -1 "$BACKUP_DIR"/vpn_bot_*.db.gz 2>/dev/null | wc -l)"
    echo "Размер всех бэкапов: $(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)"
}

# Функция автоматического бэкапа (для cron)
auto_backup() {
    create_backup >> "$BACKUP_DIR/backup.log" 2>&1
}

# Главное меню
case "$1" in
    backup)
        create_backup
        ;;
    restore)
        restore_backup
        ;;
    export)
        export_to_csv
        ;;
    stats)
        show_stats
        ;;
    auto)
        auto_backup
        ;;
    *)
        echo "VPN Bot - Управление базой данных"
        echo "================================="
        echo ""
        echo "Использование: $0 {backup|restore|export|stats|auto}"
        echo ""
        echo "  backup  - Создать резервную копию"
        echo "  restore - Восстановить из резервной копии"
        echo "  export  - Экспортировать данные в CSV"
        echo "  stats   - Показать статистику"
        echo "  auto    - Автоматический бэкап (для cron)"
        echo ""
        echo "Для автоматического бэкапа добавьте в crontab:"
        echo "0 3 * * * $0 auto"
        exit 1
        ;;
esac
