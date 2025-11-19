# VPN Telegram Bot для XTLS-Reality

Полностью автоматизированный Telegram бот для управления VPN подписками на базе Xray с протоколом VLESS + XTLS-Reality.

## 🚀 Возможности

### Для пользователей:
- 🎁 Автоматический пробный период
- 🔑 Мгновенная выдача ключей VPN
- 📱 QR-коды для быстрой настройки
- 📊 Отслеживание статуса подписки
- 💳 Простая система оплаты
- 📖 Встроенные инструкции

### Для администратора:
- 👥 Управление пользователями
- 📈 Статистика и аналитика
- 🔄 Автоматическое управление Xray
- 💰 Контроль платежей
- 🔧 Мониторинг состояния сервера
- 📝 Логирование всех действий
- 💾 Автоматическое резервное копирование

## 📋 Требования

- ✅ Настроенный Xray сервер с VLESS + XTLS-Reality (по инструкции из глав 1-7)
- ✅ Debian 10+ или Ubuntu 20.04+
- ✅ Python 3.8+
- ✅ Root доступ к серверу
- ✅ Telegram Bot Token от @BotFather
- ✅ Ваш Telegram ID от @userinfobot

## 🛠 Установка

### Автоматическая установка (рекомендуется):

```bash
# Скачиваем скрипт установки
wget https://raw.githubusercontent.com/yourusername/vpn-bot/main/install_bot.sh

# Делаем исполняемым
chmod +x install_bot.sh

# Запускаем установку
sudo ./install_bot.sh
```

### Ручная установка:

1. **Клонируем репозиторий:**
```bash
cd /home/universal
git clone https://github.com/yourusername/vpn-bot.git
cd vpn-bot
```

2. **Создаем виртуальное окружение:**
```bash
python3 -m venv venv
source venv/bin/activate
```

3. **Устанавливаем зависимости:**
```bash
pip install -r requirements.txt
```

4. **Настраиваем конфигурацию:**
```bash
nano vpn_bot.py
# Измените следующие параметры:
# BOT_TOKEN = "ваш_токен_от_botfather"
# ADMIN_IDS = [ваш_telegram_id]
# SERVER_DOMAIN = "ваш.домен.com"
```

5. **Создаем systemd сервис:**
```bash
sudo nano /etc/systemd/system/vpn-bot.service
```

Вставьте содержимое из файла `vpn-bot.service`

6. **Запускаем бота:**
```bash
sudo systemctl enable vpn-bot
sudo systemctl start vpn-bot
```

## ⚙️ Конфигурация

### Основные параметры в `vpn_bot.py`:

| Параметр | Описание | Пример |
|----------|----------|--------|
| `BOT_TOKEN` | Токен от @BotFather | "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz" |
| `ADMIN_IDS` | Список ID администраторов | [123456789, 987654321] |
| `SERVER_DOMAIN` | Домен вашего VPN сервера | "vpn.example.com" |
| `SERVER_PORT` | Порт Xray сервера | 443 |
| `TRIAL_DAYS` | Длительность пробного периода | 3 |
| `SUBSCRIPTION_PRICE` | Стоимость месячной подписки | 500 |
| `PAYMENT_CARD` | Номер карты для оплаты | "1234 5678 9012 3456" |

### Пути к файлам:

| Файл | Путь | Описание |
|------|------|----------|
| Конфигурация Xray | `/usr/local/etc/xray/config.json` | Основной конфиг Xray |
| База данных бота | `/home/universal/vpn_bot/database.json` | Данные пользователей |
| Логи бота | `/home/universal/vpn_bot/logs/bot.log` | Журнал работы |
| Резервные копии | `/home/universal/vpn_bot/backups/` | Бэкапы БД и конфигов |

## 💬 Команды бота

### Для пользователей:
- `/start` - Главное меню
- `🔑 Получить ключ` - Получить VPN конфигурацию
- `📊 Мой статус` - Информация о подписке
- `💳 Продлить подписку` - Оплата
- `📖 Инструкция` - Помощь по настройке

### Для администратора:
- `👨‍💼 Админ панель` - Управление ботом
- `👥 Пользователи` - Список всех пользователей
- `📊 Статистика` - Общая статистика
- `🔄 Перезапуск Xray` - Перезапустить сервер
- `📝 Логи` - Просмотр последних логов

## 🔧 Управление ботом

```bash
# Статус бота
vpn-bot status

# Перезапуск
vpn-bot restart

# Остановка
vpn-bot stop

# Запуск
vpn-bot start

# Просмотр логов в реальном времени
vpn-bot logs

# Создание резервной копии
vpn-bot backup

# Обновление зависимостей
vpn-bot update
```

## 💳 Процесс оплаты

1. Пользователь нажимает "Оплатить"
2. Бот показывает реквизиты для оплаты
3. Пользователь переводит деньги и нажимает "Оплатил"
4. Администратор получает уведомление
5. Администратор подтверждает или отклоняет платеж
6. Пользователь получает доступ на 30 дней

### Автоматизация платежей (опционально):

Для полной автоматизации можно подключить:
- YooMoney API
- Cryptobot
- Telegram Payments API
- QIWI API

## 🔄 Автоматические функции

### Проверка подписок (каждый час):
- Предупреждение за 3 дня до окончания
- Автоматическое отключение истекших подписок
- Удаление ключей из Xray конфигурации

### Мониторинг Xray (каждые 5 минут):
- Проверка статуса сервиса
- Автоматический перезапуск при сбое
- Уведомление администратора о проблемах

### Резервное копирование (ежедневно в 3:00):
- Сохранение базы данных
- Копирование конфигурации Xray
- Удаление старых бэкапов (>7 дней)

## 📊 База данных

Структура `database.json`:

```json
{
  "users": {
    "123456789": {
      "username": "username",
      "created_at": "2024-01-01T00:00:00",
      "subscription_end": "2024-02-01T00:00:00",
      "is_trial_used": false,
      "is_active": true,
      "total_paid": 500,
      "configs": ["uuid-1234-5678"]
    }
  },
  "configs": {
    "123456789": [{
      "uuid": "uuid-1234-5678",
      "name": "default",
      "created_at": "2024-01-01T00:00:00",
      "traffic_used": 0,
      "last_seen": null
    }]
  },
  "payments": {
    "123456789": [{
      "amount": 500,
      "date": "2024-01-01T00:00:00",
      "confirmed": true
    }]
  }
}
```

## 🚨 Решение проблем

### Бот не запускается:
```bash
# Проверьте логи
sudo journalctl -u vpn-bot -n 50

# Проверьте права на файлы
ls -la /home/universal/vpn_bot/

# Проверьте Python
python3 --version
```

### Не выдаются ключи:
```bash
# Проверьте Xray
sudo systemctl status xray

# Проверьте конфигурацию
sudo xray run -test -c /usr/local/etc/xray/config.json

# Проверьте права на редактирование
sudo chmod 666 /usr/local/etc/xray/config.json
```

### Не работает перезапуск Xray:
```bash
# Добавьте права в sudoers
sudo visudo
# Добавьте строку:
universal ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart xray
```

## 🔐 Безопасность

### Рекомендации:
1. **Используйте сложный токен бота** - не делитесь им
2. **Ограничьте доступ к файлам** - `chmod 600` для конфигов
3. **Регулярные бэкапы** - настройте внешнее хранилище
4. **Мониторинг логов** - проверяйте подозрительную активность
5. **Обновления** - следите за обновлениями aiogram и Xray

### Защита от атак:
- Rate limiting встроен в aiogram
- Валидация всех входных данных
- Логирование всех критических действий
- Автоматическая блокировка при подозрительной активности

## 📝 Логирование

Все действия логируются в файлы:
- `/home/universal/vpn_bot/logs/bot.log` - основной лог
- `/home/universal/vpn_bot/logs/bot.error.log` - ошибки
- `/var/log/xray/access.log` - доступ к Xray
- `/var/log/xray/error.log` - ошибки Xray

Просмотр логов:
```bash
# Логи бота
tail -f /home/universal/vpn_bot/logs/bot.log

# Логи Xray
tail -f /var/log/xray/access.log

# Системные логи
journalctl -u vpn-bot -f
```

## 🔄 Обновление

### Обновление бота:
```bash
cd /home/universal/vpn_bot
git pull
source venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl restart vpn-bot
```

### Обновление Xray:
```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)"
sudo systemctl restart xray
sudo systemctl restart vpn-bot
```

## 🤝 Поддержка

- Telegram: @your_support_username
- GitHub Issues: https://github.com/yourusername/vpn-bot/issues
- Email: support@example.com

## 📄 Лицензия

MIT License - свободное использование и модификация

## 🙏 Благодарности

- [XTLS/Xray-core](https://github.com/XTLS/Xray-core) - за отличный VPN протокол
- [aiogram](https://github.com/aiogram/aiogram) - за удобный фреймворк для Telegram
- Сообществу за поддержку и тестирование

---

**⚠️ Дисклеймер:** Используйте VPN в соответствии с законодательством вашей страны. Автор не несет ответственности за неправомерное использование.
