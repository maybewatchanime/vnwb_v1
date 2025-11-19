#!/usr/bin/env python3
"""
Telegram VPN Bot - Автоматизированная система управления VPN подписками
Поддерживает XTLS-Reality конфигурацию с автоматической выдачей ключей
"""

import os
import json
import uuid
import asyncio
import logging
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import aiofiles
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
import qrcode
from io import BytesIO
import base64

# ===== КОНФИГУРАЦИЯ =====
BOT_TOKEN = "YOUR_BOT_TOKEN"  # Токен от @BotFather
ADMIN_IDS = [123456789]  # Ваш Telegram ID

# Настройки сервера
SERVER_DOMAIN = "your.domain.com"  # Ваш домен
SERVER_PORT = 443
SERVER_IP = "100.200.300.400"  # IP вашего сервера

# Пути к файлам
XRAY_CONFIG_PATH = "/usr/local/etc/xray/config.json"
XRAY_CONFIG_BACKUP = "/usr/local/etc/xray/config.backup.json"
DATABASE_PATH = "/home/universal/vpn_bot/database.json"
LOGS_PATH = "/home/universal/vpn_bot/bot.log"

# Настройки подписки
TRIAL_DAYS = 3  # Пробный период в днях
SUBSCRIPTION_PRICE = 500  # Цена подписки в рублях
PAYMENT_CARD = "1234 5678 9012 3456"  # Номер карты для оплаты

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOGS_PATH),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ===== СОСТОЯНИЯ FSM =====
class UserStates(StatesGroup):
    waiting_for_payment = State()
    waiting_for_payment_confirmation = State()
    selecting_plan = State()

# ===== БАЗА ДАННЫХ =====
class Database:
    def __init__(self, path: str):
        self.path = path
        self.data = self.load()
    
    def load(self) -> Dict:
        """Загрузка базы данных из файла"""
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    return json.load(f)
            except:
                return {"users": {}, "configs": {}, "payments": {}}
        return {"users": {}, "configs": {}, "payments": {}}
    
    async def save(self):
        """Асинхронное сохранение базы данных"""
        async with aiofiles.open(self.path, 'w') as f:
            await f.write(json.dumps(self.data, indent=2, ensure_ascii=False))
    
    def get_user(self, user_id: str) -> Optional[Dict]:
        """Получить данные пользователя"""
        return self.data["users"].get(str(user_id))
    
    async def add_user(self, user_id: int, username: str = None) -> Dict:
        """Добавить нового пользователя"""
        user_id = str(user_id)
        if user_id not in self.data["users"]:
            self.data["users"][user_id] = {
                "username": username,
                "created_at": datetime.now().isoformat(),
                "subscription_end": None,
                "is_trial_used": False,
                "is_active": False,
                "total_paid": 0,
                "configs": []
            }
            await self.save()
        return self.data["users"][user_id]
    
    async def add_config(self, user_id: int, config_uuid: str, name: str = "default"):
        """Добавить конфигурацию пользователю"""
        user_id = str(user_id)
        config_data = {
            "uuid": config_uuid,
            "name": name,
            "created_at": datetime.now().isoformat(),
            "traffic_used": 0,
            "last_seen": None
        }
        
        if user_id not in self.data["configs"]:
            self.data["configs"][user_id] = []
        
        self.data["configs"][user_id].append(config_data)
        
        if user_id in self.data["users"]:
            self.data["users"][user_id]["configs"].append(config_uuid)
        
        await self.save()
        return config_data

# ===== XRAY MANAGER =====
class XrayManager:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.backup_path = config_path + ".backup"
    
    async def load_config(self) -> Dict:
        """Загрузить конфигурацию Xray"""
        async with aiofiles.open(self.config_path, 'r') as f:
            content = await f.read()
            return json.loads(content)
    
    async def save_config(self, config: Dict):
        """Сохранить конфигурацию Xray"""
        # Создаем резервную копию
        await self.backup_config()
        
        # Сохраняем новую конфигурацию
        async with aiofiles.open(self.config_path, 'w') as f:
            await f.write(json.dumps(config, indent=2, ensure_ascii=False))
    
    async def backup_config(self):
        """Создать резервную копию конфигурации"""
        config = await self.load_config()
        async with aiofiles.open(self.backup_path, 'w') as f:
            await f.write(json.dumps(config, indent=2, ensure_ascii=False))
    
    async def add_user(self, user_uuid: str, email: str = None) -> bool:
        """Добавить пользователя в конфигурацию Xray"""
        try:
            config = await self.load_config()
            
            # Находим нужный inbound (VLESS)
            for inbound in config["inbounds"]:
                if inbound.get("protocol") == "vless":
                    client = {
                        "id": user_uuid,
                        "flow": "xtls-rprx-vision",
                        "level": 0,
                        "email": email or f"user_{user_uuid[:8]}@vpn.local"
                    }
                    
                    # Добавляем клиента если его еще нет
                    if not any(c["id"] == user_uuid for c in inbound["settings"]["clients"]):
                        inbound["settings"]["clients"].append(client)
                        await self.save_config(config)
                        await self.restart_xray()
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Error adding user to Xray: {e}")
            return False
    
    async def remove_user(self, user_uuid: str) -> bool:
        """Удалить пользователя из конфигурации Xray"""
        try:
            config = await self.load_config()
            
            for inbound in config["inbounds"]:
                if inbound.get("protocol") == "vless":
                    clients = inbound["settings"]["clients"]
                    inbound["settings"]["clients"] = [
                        c for c in clients if c["id"] != user_uuid
                    ]
            
            await self.save_config(config)
            await self.restart_xray()
            return True
        except Exception as e:
            logger.error(f"Error removing user from Xray: {e}")
            return False
    
    async def restart_xray(self):
        """Перезапустить сервис Xray"""
        try:
            subprocess.run(["sudo", "systemctl", "restart", "xray"], check=True)
            await asyncio.sleep(2)  # Ждем пока сервис перезапустится
            return True
        except:
            return False
    
    async def check_status(self) -> bool:
        """Проверить статус сервиса Xray"""
        try:
            result = subprocess.run(
                ["sudo", "systemctl", "is-active", "xray"],
                capture_output=True,
                text=True
            )
            return result.stdout.strip() == "active"
        except:
            return False

# ===== ГЕНЕРАТОР ССЫЛОК =====
class LinkGenerator:
    @staticmethod
    def generate_vless_link(user_uuid: str, domain: str, port: int = 443) -> str:
        """Генерация VLESS ссылки для подключения"""
        # Формат: vless://UUID@SERVER:PORT?параметры#название
        params = {
            "encryption": "none",
            "security": "tls",
            "sni": domain,
            "fp": "chrome",
            "type": "tcp",
            "flow": "xtls-rprx-vision"
        }
        
        params_str = "&".join([f"{k}={v}" for k, v in params.items()])
        link = f"vless://{user_uuid}@{domain}:{port}?{params_str}#VPN-{domain}"
        
        return link
    
    @staticmethod
    async def generate_qr_code(text: str) -> BytesIO:
        """Генерация QR-кода"""
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(text)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        
        return bio
    
    @staticmethod
    def generate_clash_config(user_uuid: str, domain: str, port: int = 443) -> str:
        """Генерация конфигурации для Clash"""
        config = {
            "proxies": [{
                "name": f"VPN-{domain}",
                "type": "vless",
                "server": domain,
                "port": port,
                "uuid": user_uuid,
                "tls": True,
                "servername": domain,
                "network": "tcp",
                "flow": "xtls-rprx-vision",
                "skip-cert-verify": False
            }]
        }
        return json.dumps(config, indent=2)

# ===== ИНИЦИАЛИЗАЦИЯ =====
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
db = Database(DATABASE_PATH)
xray_manager = XrayManager(XRAY_CONFIG_PATH)
link_gen = LinkGenerator()

# ===== КЛАВИАТУРЫ =====
def get_main_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главное меню"""
    buttons = [
        [InlineKeyboardButton(text="🔑 Получить ключ", callback_data="get_key")],
        [InlineKeyboardButton(text="📊 Мой статус", callback_data="status")],
        [InlineKeyboardButton(text="💳 Продлить подписку", callback_data="payment")],
        [InlineKeyboardButton(text="📖 Инструкция", callback_data="help")],
    ]
    
    if is_admin:
        buttons.append([InlineKeyboardButton(text="👨‍💼 Админ панель", callback_data="admin")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_payment_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура оплаты"""
    buttons = [
        [InlineKeyboardButton(text="💳 Оплатил", callback_data="paid")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Админ панель"""
    buttons = [
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🔄 Перезапуск Xray", callback_data="admin_restart")],
        [InlineKeyboardButton(text="📝 Логи", callback_data="admin_logs")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ===== ОБРАБОТЧИКИ КОМАНД =====
@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Команда /start"""
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Добавляем пользователя в базу если его нет
    await db.add_user(user_id, username)
    
    is_admin = user_id in ADMIN_IDS
    
    welcome_text = f"""
🚀 **Добро пожаловать в VPN Bot!**

Этот бот предоставляет доступ к высокоскоростному VPN серверу с протоколом VLESS + XTLS-Reality.

✨ **Возможности:**
• Скорость до 1 Гбит/с
• Без логирования трафика
• Стабильное соединение 24/7
• Поддержка всех платформ
• Пробный период {TRIAL_DAYS} дня

💰 **Стоимость:** {SUBSCRIPTION_PRICE}₽/месяц

Выберите действие:
"""
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(is_admin),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "get_key")
async def get_key_handler(callback: CallbackQuery):
    """Получение ключа"""
    user_id = callback.from_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        await db.add_user(user_id, callback.from_user.username)
        user_data = db.get_user(user_id)
    
    # Проверяем активную подписку
    if user_data.get("subscription_end"):
        sub_end = datetime.fromisoformat(user_data["subscription_end"])
        if sub_end > datetime.now():
            # Подписка активна, выдаем ключ
            configs = db.data["configs"].get(str(user_id), [])
            
            if configs:
                # Используем существующий ключ
                config = configs[0]
                user_uuid = config["uuid"]
            else:
                # Создаем новый ключ
                user_uuid = str(uuid.uuid4())
                await db.add_config(user_id, user_uuid)
                await xray_manager.add_user(user_uuid, f"user_{user_id}@vpn.local")
            
            # Генерируем ссылку
            vless_link = link_gen.generate_vless_link(user_uuid, SERVER_DOMAIN, SERVER_PORT)
            
            # Генерируем QR-код
            qr_bio = await link_gen.generate_qr_code(vless_link)
            
            instructions = f"""
✅ **Ваш VPN ключ готов!**

📅 Подписка активна до: {sub_end.strftime('%d.%m.%Y')}

**Ссылка для подключения:**
`{vless_link}`

📱 **Приложения для подключения:**
• iOS: Shadowrocket, Surge
• Android: v2rayNG, Surfboard
• Windows: v2rayN, Clash
• macOS: V2RayXS, ClashX

📖 **Инструкция:**
1. Установите одно из приложений выше
2. Скопируйте ссылку или отсканируйте QR-код
3. Добавьте конфигурацию в приложение
4. Включите VPN

⚠️ **Важно:** Не делитесь своим ключом с другими!
"""
            
            await callback.message.answer_photo(
                qr_bio,
                caption=instructions,
                parse_mode="Markdown"
            )
            
        else:
            # Подписка истекла
            await callback.answer("❌ Ваша подписка истекла. Пожалуйста, продлите её.", show_alert=True)
            await payment_handler(callback)
    
    elif not user_data.get("is_trial_used"):
        # Активируем пробный период
        user_data["is_trial_used"] = True
        user_data["subscription_end"] = (datetime.now() + timedelta(days=TRIAL_DAYS)).isoformat()
        user_data["is_active"] = True
        await db.save()
        
        # Создаем ключ
        user_uuid = str(uuid.uuid4())
        await db.add_config(user_id, user_uuid)
        await xray_manager.add_user(user_uuid, f"user_{user_id}@vpn.local")
        
        # Генерируем ссылку
        vless_link = link_gen.generate_vless_link(user_uuid, SERVER_DOMAIN, SERVER_PORT)
        
        # Генерируем QR-код
        qr_bio = await link_gen.generate_qr_code(vless_link)
        
        trial_end = datetime.now() + timedelta(days=TRIAL_DAYS)
        
        instructions = f"""
🎉 **Пробный период активирован!**

Вы получили бесплатный доступ на {TRIAL_DAYS} дня.
📅 Действует до: {trial_end.strftime('%d.%m.%Y')}

**Ваша ссылка для подключения:**
`{vless_link}`

📱 **Приложения для подключения:**
• iOS: Shadowrocket, Surge
• Android: v2rayNG, Surfboard
• Windows: v2rayN, Clash
• macOS: V2RayXS, ClashX

📖 **Быстрая настройка:**
1. Установите приложение из списка
2. Отсканируйте QR-код или скопируйте ссылку
3. Включите VPN

💡 После окончания пробного периода вы сможете продлить подписку за {SUBSCRIPTION_PRICE}₽/месяц
"""
        
        await callback.message.answer_photo(
            qr_bio,
            caption=instructions,
            parse_mode="Markdown"
        )
    
    else:
        # Пробный период использован, нужна оплата
        await callback.answer("❌ Пробный период уже использован. Необходима оплата.", show_alert=True)
        await payment_handler(callback)
    
    await callback.answer()

@dp.callback_query(F.data == "status")
async def status_handler(callback: CallbackQuery):
    """Статус пользователя"""
    user_id = callback.from_user.id
    user_data = db.get_user(user_id)
    
    if not user_data:
        await callback.answer("❌ Пользователь не найден", show_alert=True)
        return
    
    # Проверяем статус подписки
    status = "❌ Неактивна"
    days_left = 0
    
    if user_data.get("subscription_end"):
        sub_end = datetime.fromisoformat(user_data["subscription_end"])
        if sub_end > datetime.now():
            status = "✅ Активна"
            days_left = (sub_end - datetime.now()).days
    
    configs_count = len(db.data["configs"].get(str(user_id), []))
    
    status_text = f"""
📊 **Ваш статус**

👤 **ID:** `{user_id}`
📛 **Username:** @{callback.from_user.username or 'не указан'}
📅 **Регистрация:** {datetime.fromisoformat(user_data['created_at']).strftime('%d.%m.%Y')}

💎 **Подписка:** {status}
⏳ **Осталось дней:** {days_left}
🔑 **Активных ключей:** {configs_count}
💰 **Всего оплачено:** {user_data['total_paid']}₽
🎁 **Пробный период:** {'Использован' if user_data['is_trial_used'] else 'Доступен'}
"""
    
    buttons = []
    if days_left <= 3 and days_left > 0:
        buttons.append([InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="payment")])
    elif days_left == 0 and not user_data.get("is_trial_used"):
        buttons.append([InlineKeyboardButton(text="🎁 Активировать пробный период", callback_data="get_key")])
    elif days_left == 0:
        buttons.append([InlineKeyboardButton(text="💳 Оплатить подписку", callback_data="payment")])
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
    
    await callback.message.edit_text(
        status_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "payment")
async def payment_handler(callback: CallbackQuery, state: FSMContext):
    """Оплата подписки"""
    user_id = callback.from_user.id
    
    payment_text = f"""
💳 **Оплата подписки**

**Стоимость:** {SUBSCRIPTION_PRICE}₽ за 30 дней

**Способы оплаты:**

1️⃣ **Перевод на карту:**
`{PAYMENT_CARD}`

2️⃣ **СБП по номеру телефона:**
+7 (XXX) XXX-XX-XX

**Инструкция:**
1. Переведите {SUBSCRIPTION_PRICE}₽ одним из способов выше
2. Нажмите кнопку "💳 Оплатил"
3. Дождитесь подтверждения (обычно 1-5 минут)

⚠️ **В комментарии к переводу укажите:** `{user_id}`
"""
    
    await state.set_state(UserStates.waiting_for_payment)
    await state.update_data(payment_amount=SUBSCRIPTION_PRICE)
    
    await callback.message.edit_text(
        payment_text,
        reply_markup=get_payment_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "paid")
async def paid_handler(callback: CallbackQuery, state: FSMContext):
    """Подтверждение оплаты"""
    user_id = callback.from_user.id
    
    # Уведомляем админов
    for admin_id in ADMIN_IDS:
        try:
            admin_text = f"""
💰 **Новая оплата!**

👤 Пользователь: {callback.from_user.full_name}
🆔 ID: `{user_id}`
📛 Username: @{callback.from_user.username or 'не указан'}
💵 Сумма: {SUBSCRIPTION_PRICE}₽

Подтвердить оплату?
"""
            confirm_buttons = [
                [
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_payment_{user_id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_payment_{user_id}")
                ]
            ]
            
            await bot.send_message(
                admin_id,
                admin_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=confirm_buttons),
                parse_mode="Markdown"
            )
        except:
            pass
    
    await state.clear()
    
    await callback.message.edit_text(
        "⏳ Проверяем оплату...\n\nОбычно это занимает 1-5 минут.\nВы получите уведомление о результате.",
        parse_mode="Markdown"
    )
    await callback.answer("Запрос отправлен администратору", show_alert=True)

@dp.callback_query(F.data.startswith("confirm_payment_"))
async def confirm_payment(callback: CallbackQuery):
    """Подтверждение оплаты админом"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    user_data = db.get_user(user_id)
    
    if user_data:
        # Продлеваем подписку
        current_end = user_data.get("subscription_end")
        if current_end:
            current_end = datetime.fromisoformat(current_end)
            if current_end > datetime.now():
                new_end = current_end + timedelta(days=30)
            else:
                new_end = datetime.now() + timedelta(days=30)
        else:
            new_end = datetime.now() + timedelta(days=30)
        
        user_data["subscription_end"] = new_end.isoformat()
        user_data["is_active"] = True
        user_data["total_paid"] += SUBSCRIPTION_PRICE
        await db.save()
        
        # Если у пользователя нет ключа, создаем
        configs = db.data["configs"].get(str(user_id), [])
        if not configs:
            user_uuid = str(uuid.uuid4())
            await db.add_config(user_id, user_uuid)
            await xray_manager.add_user(user_uuid, f"user_{user_id}@vpn.local")
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"✅ **Оплата подтверждена!**\n\nВаша подписка продлена до {new_end.strftime('%d.%m.%Y')}\n\nИспользуйте /start для получения ключа.",
                parse_mode="Markdown"
            )
        except:
            pass
        
        await callback.message.edit_text(
            callback.message.text + "\n\n✅ **ПОДТВЕРЖДЕНО**",
            parse_mode="Markdown"
        )
        await callback.answer("✅ Оплата подтверждена")
    else:
        await callback.answer("❌ Пользователь не найден", show_alert=True)

@dp.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(callback: CallbackQuery):
    """Отклонение оплаты админом"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return
    
    user_id = int(callback.data.split("_")[-1])
    
    # Уведомляем пользователя
    try:
        await bot.send_message(
            user_id,
            "❌ **Оплата не найдена**\n\nПожалуйста, проверьте правильность перевода и попробуйте снова.",
            parse_mode="Markdown"
        )
    except:
        pass
    
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ **ОТКЛОНЕНО**",
        parse_mode="Markdown"
    )
    await callback.answer("❌ Оплата отклонена")

@dp.callback_query(F.data == "help")
async def help_handler(callback: CallbackQuery):
    """Инструкция"""
    help_text = """
📖 **Инструкция по подключению**

**🍎 iOS (iPhone/iPad):**
1. Установите Shadowrocket из App Store
2. Нажмите "+" → "Type" → "Subscribe"
3. Вставьте ссылку и сохраните
4. Включите VPN

**🤖 Android:**
1. Установите v2rayNG из Google Play
2. Нажмите "+" → "Импорт из буфера"
3. Вставьте ссылку
4. Нажмите на галочку для подключения

**💻 Windows:**
1. Скачайте v2rayN с GitHub
2. Нажмите "Серверы" → "Добавить из буфера"
3. Вставьте ссылку
4. Нажмите Enter для подключения

**🖥 macOS:**
1. Установите V2RayXS или ClashX
2. Импортируйте конфигурацию
3. Включите системный прокси

**❓ Частые вопросы:**

*Почему не подключается?*
• Проверьте срок подписки
• Попробуйте другое приложение
• Перезагрузите устройство

*Низкая скорость?*
• Проверьте скорость без VPN
• Попробуйте сменить сервер в настройках
• Используйте проводное подключение

**💬 Поддержка:** @your_support_username
"""
    
    buttons = [[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]
    
    await callback.message.edit_text(
        help_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin")
async def admin_panel(callback: CallbackQuery):
    """Админ панель"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return
    
    await callback.message.edit_text(
        "👨‍💼 **Админ панель**\n\nВыберите действие:",
        reply_markup=get_admin_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Статистика для админа"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return
    
    total_users = len(db.data["users"])
    active_users = sum(1 for u in db.data["users"].values() if u.get("is_active"))
    trial_users = sum(1 for u in db.data["users"].values() if u.get("is_trial_used"))
    total_revenue = sum(u.get("total_paid", 0) for u in db.data["users"].values())
    
    # Проверяем статус Xray
    xray_status = "✅ Работает" if await xray_manager.check_status() else "❌ Остановлен"
    
    stats_text = f"""
📊 **Статистика**

**Пользователи:**
👥 Всего: {total_users}
✅ Активных: {active_users}
🎁 Использовали триал: {trial_users}

**Финансы:**
💰 Общий доход: {total_revenue}₽
💵 Средний чек: {total_revenue // max(active_users, 1)}₽

**Система:**
🔧 Xray: {xray_status}
💾 Размер БД: {os.path.getsize(DATABASE_PATH) / 1024:.2f} KB
"""
    
    buttons = [[InlineKeyboardButton(text="🔙 Назад", callback_data="admin")]]
    
    await callback.message.edit_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_restart")
async def admin_restart_xray(callback: CallbackQuery):
    """Перезапуск Xray"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return
    
    await callback.answer("⏳ Перезапускаю Xray...")
    
    if await xray_manager.restart_xray():
        status = "✅ Работает" if await xray_manager.check_status() else "❌ Ошибка"
        await callback.answer(f"Xray перезапущен. Статус: {status}", show_alert=True)
    else:
        await callback.answer("❌ Ошибка при перезапуске", show_alert=True)

@dp.callback_query(F.data == "back")
async def back_to_main(callback: CallbackQuery):
    """Возврат в главное меню"""
    is_admin = callback.from_user.id in ADMIN_IDS
    
    await callback.message.edit_text(
        "🚀 **Главное меню**\n\nВыберите действие:",
        reply_markup=get_main_keyboard(is_admin),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data == "cancel")
async def cancel_handler(callback: CallbackQuery, state: FSMContext):
    """Отмена действия"""
    await state.clear()
    is_admin = callback.from_user.id in ADMIN_IDS
    
    await callback.message.edit_text(
        "❌ Действие отменено.\n\n🚀 **Главное меню:**",
        reply_markup=get_main_keyboard(is_admin),
        parse_mode="Markdown"
    )
    await callback.answer()

# ===== ФОНОВЫЕ ЗАДАЧИ =====
async def check_subscriptions():
    """Проверка истекших подписок"""
    while True:
        try:
            for user_id, user_data in db.data["users"].items():
                if user_data.get("subscription_end"):
                    sub_end = datetime.fromisoformat(user_data["subscription_end"])
                    
                    # Предупреждение за 3 дня
                    days_left = (sub_end - datetime.now()).days
                    if days_left == 3:
                        try:
                            await bot.send_message(
                                int(user_id),
                                f"⚠️ Ваша подписка истекает через 3 дня!\n\nНе забудьте продлить её, чтобы не потерять доступ.",
                                parse_mode="Markdown"
                            )
                        except:
                            pass
                    
                    # Отключение при истечении
                    elif sub_end < datetime.now() and user_data.get("is_active"):
                        user_data["is_active"] = False
                        
                        # Удаляем пользователя из Xray
                        configs = db.data["configs"].get(user_id, [])
                        for config in configs:
                            await xray_manager.remove_user(config["uuid"])
                        
                        try:
                            await bot.send_message(
                                int(user_id),
                                "❌ Ваша подписка истекла!\n\nДоступ к VPN приостановлен. Для продления используйте /start",
                                parse_mode="Markdown"
                            )
                        except:
                            pass
                        
                        await db.save()
            
            # Проверяем каждый час
            await asyncio.sleep(3600)
            
        except Exception as e:
            logger.error(f"Error in check_subscriptions: {e}")
            await asyncio.sleep(60)

async def monitor_xray():
    """Мониторинг состояния Xray"""
    while True:
        try:
            if not await xray_manager.check_status():
                # Пытаемся перезапустить
                await xray_manager.restart_xray()
                
                # Уведомляем админов
                for admin_id in ADMIN_IDS:
                    try:
                        await bot.send_message(
                            admin_id,
                            "⚠️ Xray был перезапущен из-за сбоя!",
                            parse_mode="Markdown"
                        )
                    except:
                        pass
            
            # Проверяем каждые 5 минут
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"Error in monitor_xray: {e}")
            await asyncio.sleep(60)

# ===== ЗАПУСК БОТА =====
async def on_startup():
    """Действия при запуске бота"""
    logger.info("Bot starting...")
    
    # Создаем необходимые директории
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(LOGS_PATH), exist_ok=True)
    
    # Запускаем фоновые задачи
    asyncio.create_task(check_subscriptions())
    asyncio.create_task(monitor_xray())
    
    # Уведомляем админов о запуске
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "✅ Бот успешно запущен!",
                parse_mode="Markdown"
            )
        except:
            pass
    
    logger.info("Bot started successfully")

async def on_shutdown():
    """Действия при остановке бота"""
    logger.info("Bot shutting down...")
    
    # Уведомляем админов об остановке
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "⚠️ Бот остановлен!",
                parse_mode="Markdown"
            )
        except:
            pass
    
    await bot.session.close()
    logger.info("Bot stopped")

async def main():
    """Главная функция"""
    # Регистрируем обработчики запуска и остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
