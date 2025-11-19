#!/usr/bin/env python3
"""
Telegram бот для автоматической выдачи VPN ключей XTLS-Reality
Автор: King's VPN Service Bot
"""

import os
import json
import uuid
import qrcode
import io
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
import subprocess
import aiofiles
from pathlib import Path

from aiogram import Bot, Dispatcher, types, Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func

# Настройки
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x]
PAYMENT_CARD = os.getenv('PAYMENT_CARD', '1234567890123456')
SERVER_IP = os.getenv('SERVER_IP', '100.200.300.400')
SERVER_DOMAIN = os.getenv('SERVER_DOMAIN', 'sub.yourdomain.com')
XRAY_CONFIG_PATH = '/usr/local/etc/xray/config.json'
XRAY_SERVICE_NAME = 'xray'

# Цены подписки
PRICES = {
    '1_month': {'price': 500, 'days': 30, 'name': '1 месяц'},
    '3_months': {'price': 1350, 'days': 90, 'name': '3 месяца', 'discount': 10},
    '6_months': {'price': 2550, 'days': 180, 'name': '6 месяцев', 'discount': 15},
    '1_year': {'price': 4800, 'days': 365, 'name': '1 год', 'discount': 20}
}

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/claude/vpn_bot/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# База данных
Base = declarative_base()
engine = create_engine('sqlite:///vpn_bot.db')

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    username = Column(String)
    full_name = Column(String)
    uuid = Column(String, unique=True)
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=False)
    is_trial_used = Column(Boolean, default=False)
    total_paid = Column(Float, default=0.0)
    referrer_id = Column(Integer)
    configs_count = Column(Integer, default=1)

class Payment(Base):
    __tablename__ = 'payments'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    days = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=func.now())
    is_confirmed = Column(Boolean, default=False)
    payment_code = Column(String, unique=True)

Base.metadata.create_all(engine)
SessionLocal = sessionmaker(bind=engine)

# FSM состояния
class PaymentStates(StatesGroup):
    waiting_for_payment = State()
    waiting_for_payment_proof = State()
    waiting_for_feedback = State()

# Класс для управления Xray
class XrayManager:
    def __init__(self):
        self.config_path = XRAY_CONFIG_PATH
        
    async def load_config(self) -> dict:
        """Загрузить конфигурацию Xray"""
        async with aiofiles.open(self.config_path, 'r') as f:
            content = await f.read()
            # Удаляем комментарии из JSON
            lines = content.split('\n')
            clean_lines = []
            for line in lines:
                if '//' in line:
                    line = line[:line.index('//')]
                clean_lines.append(line)
            clean_content = '\n'.join(clean_lines)
            return json.loads(clean_content)
    
    async def save_config(self, config: dict):
        """Сохранить конфигурацию Xray"""
        async with aiofiles.open(self.config_path, 'w') as f:
            await f.write(json.dumps(config, indent=2))
    
    async def add_user(self, user_uuid: str, email: str) -> bool:
        """Добавить пользователя в конфигурацию Xray"""
        try:
            config = await self.load_config()
            
            # Находим VLESS inbound
            for inbound in config.get('inbounds', []):
                if inbound.get('protocol') == 'vless':
                    clients = inbound['settings']['clients']
                    
                    # Проверяем, не существует ли уже такой UUID
                    if any(client['id'] == user_uuid for client in clients):
                        return False
                    
                    # Добавляем нового клиента
                    clients.append({
                        "id": user_uuid,
                        "flow": "xtls-rprx-vision",
                        "level": 0,
                        "email": email
                    })
                    
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
            
            for inbound in config.get('inbounds', []):
                if inbound.get('protocol') == 'vless':
                    clients = inbound['settings']['clients']
                    original_length = len(clients)
                    inbound['settings']['clients'] = [
                        client for client in clients 
                        if client['id'] != user_uuid
                    ]
                    
                    if len(inbound['settings']['clients']) < original_length:
                        await self.save_config(config)
                        await self.restart_xray()
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Error removing user from Xray: {e}")
            return False
    
    async def restart_xray(self):
        """Перезапустить сервис Xray"""
        try:
            subprocess.run(['sudo', 'systemctl', 'restart', XRAY_SERVICE_NAME], check=True)
            await asyncio.sleep(2)  # Даем время на перезапуск
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restart Xray: {e}")
            return False
    
    async def get_xray_status(self) -> str:
        """Получить статус сервиса Xray"""
        try:
            result = subprocess.run(
                ['sudo', 'systemctl', 'status', XRAY_SERVICE_NAME],
                capture_output=True,
                text=True
            )
            if 'active (running)' in result.stdout:
                return '✅ Работает'
            else:
                return '❌ Остановлен'
        except Exception as e:
            return f'❌ Ошибка: {e}'

# Инициализация
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
xray_manager = XrayManager()

# Вспомогательные функции
def generate_payment_code() -> str:
    """Генерация уникального кода платежа"""
    return str(uuid.uuid4())[:8].upper()

def generate_vless_link(user_uuid: str) -> str:
    """Генерация VLESS ссылки для подключения"""
    link = (
        f"vless://{user_uuid}@{SERVER_DOMAIN}:443"
        f"?type=tcp&security=tls&flow=xtls-rprx-vision"
        f"&sni={SERVER_DOMAIN}"
        f"#VPN-{SERVER_DOMAIN}"
    )
    return link

async def generate_qr_code(data: str) -> BufferedInputFile:
    """Генерация QR-кода"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    
    return BufferedInputFile(img_byte_arr.read(), filename="qr_code.png")

def get_user_by_telegram_id(telegram_id: int) -> Optional[User]:
    """Получить пользователя по Telegram ID"""
    db = SessionLocal()
    try:
        return db.query(User).filter(User.telegram_id == telegram_id).first()
    finally:
        db.close()

def create_user(telegram_id: int, username: str, full_name: str) -> User:
    """Создать нового пользователя"""
    db = SessionLocal()
    try:
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            uuid=str(uuid.uuid4())
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()

def get_main_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главная клавиатура"""
    builder = InlineKeyboardBuilder()
    
    builder.button(text="🔑 Мой VPN", callback_data="my_vpn")
    builder.button(text="💳 Купить подписку", callback_data="buy_subscription")
    builder.button(text="🎁 Пробный период", callback_data="trial")
    builder.button(text="💬 Поддержка", callback_data="support")
    builder.button(text="ℹ️ Информация", callback_data="info")
    builder.button(text="👥 Реферальная программа", callback_data="referral")
    
    if is_admin:
        builder.button(text="⚙️ Админ-панель", callback_data="admin_panel")
    
    builder.adjust(2)
    return builder.as_markup()

def get_subscription_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора подписки"""
    builder = InlineKeyboardBuilder()
    
    for key, value in PRICES.items():
        discount_text = f" (-{value.get('discount', 0)}%)" if value.get('discount') else ""
        text = f"{value['name']}: {value['price']}₽{discount_text}"
        builder.button(text=text, callback_data=f"buy_{key}")
    
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

# Обработчики команд
@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    # Проверяем, есть ли пользователь в базе
    user = get_user_by_telegram_id(user_id)
    if not user:
        user = create_user(user_id, username, full_name)
        logger.info(f"New user registered: {user_id} - {username}")
    
    is_admin = user_id in ADMIN_IDS
    
    welcome_text = f"""
🚀 <b>Добро пожаловать в VPN Bot!</b>

Здравствуйте, {full_name}! 

Я помогу вам получить быстрый и безопасный VPN на основе <b>XTLS-Reality</b> - самой современной технологии обхода блокировок.

<b>Преимущества нашего VPN:</b>
✅ Высокая скорость (XTLS-Reality)
✅ Невозможно заблокировать
✅ Автоматическая настройка
✅ Поддержка 24/7
✅ Работает на всех устройствах

Выберите действие:
"""
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(is_admin),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    is_admin = callback.from_user.id in ADMIN_IDS
    
    await callback.message.edit_text(
        "🏠 <b>Главное меню</b>\n\nВыберите действие:",
        reply_markup=get_main_keyboard(is_admin),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "my_vpn")
async def my_vpn(callback: types.CallbackQuery):
    """Показать информацию о VPN пользователя"""
    user = get_user_by_telegram_id(callback.from_user.id)
    
    if not user or not user.is_active:
        text = "❌ <b>У вас нет активной подписки</b>\n\n"
        text += "Чтобы начать пользоваться VPN, приобретите подписку или активируйте пробный период."
        
        builder = InlineKeyboardBuilder()
        builder.button(text="💳 Купить подписку", callback_data="buy_subscription")
        builder.button(text="🎁 Пробный период", callback_data="trial")
        builder.button(text="🔙 Назад", callback_data="back_to_main")
        builder.adjust(1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        days_left = (user.expires_at - datetime.now()).days if user.expires_at else 0
        
        text = f"""
🔑 <b>Ваш VPN</b>

<b>Статус:</b> ✅ Активен
<b>Осталось дней:</b> {days_left}
<b>Истекает:</b> {user.expires_at.strftime('%d.%m.%Y') if user.expires_at else 'Не указано'}

<b>Выберите действие:</b>
"""
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📱 Получить конфигурацию", callback_data="get_config")
        builder.button(text="📊 QR-код", callback_data="get_qr")
        builder.button(text="📖 Инструкция", callback_data="instructions")
        builder.button(text="🔄 Продлить подписку", callback_data="buy_subscription")
        builder.button(text="🔙 Назад", callback_data="back_to_main")
        builder.adjust(2, 2, 1)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "get_config")
async def get_config(callback: types.CallbackQuery):
    """Отправить конфигурацию пользователю"""
    user = get_user_by_telegram_id(callback.from_user.id)
    
    if not user or not user.is_active:
        await callback.answer("У вас нет активной подписки!", show_alert=True)
        return
    
    vless_link = generate_vless_link(user.uuid)
    
    config_text = f"""
<b>Ваша конфигурация VPN:</b>

<b>VLESS ссылка (скопируйте целиком):</b>
<code>{vless_link}</code>

<b>Параметры для ручной настройки:</b>
📍 <b>Адрес:</b> <code>{SERVER_DOMAIN}</code>
🔌 <b>Порт:</b> <code>443</code>
🔐 <b>UUID:</b> <code>{user.uuid}</code>
📡 <b>Протокол:</b> VLESS
🌊 <b>Flow:</b> xtls-rprx-vision
🔒 <b>Шифрование:</b> none
🌐 <b>Сеть:</b> tcp
🛡 <b>Безопасность:</b> tls
🏷 <b>SNI:</b> <code>{SERVER_DOMAIN}</code>

<b>Поддерживаемые клиенты:</b>
• v2rayN (Windows)
• v2rayNG (Android)
• Shadowrocket (iOS)
• Qv2ray (Linux/Mac)
"""
    
    await callback.message.answer(config_text, parse_mode="HTML")
    await callback.answer("✅ Конфигурация отправлена!")

@router.callback_query(F.data == "get_qr")
async def get_qr(callback: types.CallbackQuery):
    """Отправить QR-код конфигурации"""
    user = get_user_by_telegram_id(callback.from_user.id)
    
    if not user or not user.is_active:
        await callback.answer("У вас нет активной подписки!", show_alert=True)
        return
    
    vless_link = generate_vless_link(user.uuid)
    qr_file = await generate_qr_code(vless_link)
    
    await callback.message.answer_photo(
        photo=qr_file,
        caption="📊 <b>QR-код вашей конфигурации</b>\n\nСканируйте в приложении v2rayNG или Shadowrocket",
        parse_mode="HTML"
    )
    await callback.answer("✅ QR-код отправлен!")

@router.callback_query(F.data == "trial")
async def trial_period(callback: types.CallbackQuery):
    """Активация пробного периода"""
    user = get_user_by_telegram_id(callback.from_user.id)
    
    if user.is_trial_used:
        await callback.answer("Вы уже использовали пробный период!", show_alert=True)
        return
    
    # Активируем пробный период на 3 дня
    db = SessionLocal()
    try:
        user.is_active = True
        user.is_trial_used = True
        user.expires_at = datetime.now() + timedelta(days=3)
        db.add(user)
        db.commit()
        
        # Добавляем пользователя в Xray
        email = f"{user.username or user.telegram_id}@trial"
        success = await xray_manager.add_user(user.uuid, email)
        
        if success:
            text = """
🎁 <b>Пробный период активирован!</b>

Вам доступен VPN на 3 дня бесплатно.

Теперь вы можете получить конфигурацию и начать пользоваться VPN.
"""
            builder = InlineKeyboardBuilder()
            builder.button(text="📱 Получить конфигурацию", callback_data="get_config")
            builder.button(text="📊 QR-код", callback_data="get_qr")
            builder.button(text="📖 Инструкция", callback_data="instructions")
            builder.button(text="🔙 Назад", callback_data="back_to_main")
            builder.adjust(1)
            
            await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
            logger.info(f"Trial activated for user {user.telegram_id}")
        else:
            await callback.answer("Ошибка активации. Обратитесь в поддержку.", show_alert=True)
            
    finally:
        db.close()

@router.callback_query(F.data == "buy_subscription")
async def buy_subscription(callback: types.CallbackQuery):
    """Покупка подписки"""
    text = """
💳 <b>Выберите тариф:</b>

Все тарифы включают:
✅ Безлимитный трафик
✅ Максимальная скорость
✅ Поддержка всех устройств
✅ Техническая поддержка 24/7
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=get_subscription_keyboard(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("buy_"))
async def process_purchase(callback: types.CallbackQuery, state: FSMContext):
    """Обработка покупки подписки"""
    plan_key = callback.data.replace("buy_", "")
    
    if plan_key not in PRICES:
        return
    
    plan = PRICES[plan_key]
    payment_code = generate_payment_code()
    
    # Создаем платеж в базе
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(callback.from_user.id)
        payment = Payment(
            user_id=user.id,
            amount=plan['price'],
            days=plan['days'],
            payment_code=payment_code
        )
        db.add(payment)
        db.commit()
    finally:
        db.close()
    
    # Сохраняем данные в состоянии
    await state.update_data(
        payment_code=payment_code,
        plan_key=plan_key,
        amount=plan['price'],
        days=plan['days']
    )
    
    text = f"""
💳 <b>Оплата подписки</b>

<b>Тариф:</b> {plan['name']}
<b>Стоимость:</b> {plan['price']} ₽
<b>Код платежа:</b> <code>{payment_code}</code>

<b>Инструкция по оплате:</b>
1. Переведите {plan['price']} ₽ на карту:
<code>{PAYMENT_CARD}</code>

2. <b>В комментарии к переводу обязательно укажите код:</b>
<code>{payment_code}</code>

3. После перевода нажмите кнопку "Я оплатил"

⚠️ <b>Важно:</b> Обязательно укажите код платежа в комментарии к переводу!
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Я оплатил", callback_data="payment_done")
    builder.button(text="❌ Отменить", callback_data="cancel_payment")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(PaymentStates.waiting_for_payment)

@router.callback_query(F.data == "payment_done", PaymentStates.waiting_for_payment)
async def payment_done(callback: types.CallbackQuery, state: FSMContext):
    """Подтверждение оплаты"""
    data = await state.get_data()
    payment_code = data.get('payment_code')
    
    text = f"""
📸 <b>Подтверждение оплаты</b>

Пожалуйста, отправьте скриншот перевода для подтверждения оплаты.

<b>Код вашего платежа:</b> <code>{payment_code}</code>

После проверки платежа (обычно до 5 минут) ваша подписка будет активирована автоматически.
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить", callback_data="cancel_payment")
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(PaymentStates.waiting_for_payment_proof)
    
    # Уведомляем админов
    for admin_id in ADMIN_IDS:
        try:
            admin_text = f"""
🔔 <b>Новый платеж!</b>

<b>Пользователь:</b> @{callback.from_user.username or 'no_username'}
<b>ID:</b> {callback.from_user.id}
<b>Код платежа:</b> <code>{payment_code}</code>
<b>Сумма:</b> {data['amount']} ₽
<b>Тариф:</b> {data['days']} дней

Ожидается подтверждение оплаты.
"""
            await bot.send_message(admin_id, admin_text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

@router.message(PaymentStates.waiting_for_payment_proof, F.photo)
async def process_payment_proof(message: types.Message, state: FSMContext):
    """Обработка скриншота оплаты"""
    data = await state.get_data()
    payment_code = data.get('payment_code')
    
    # Пересылаем скриншот админам
    for admin_id in ADMIN_IDS:
        try:
            await message.forward(admin_id)
            
            admin_builder = InlineKeyboardBuilder()
            admin_builder.button(
                text="✅ Подтвердить оплату",
                callback_data=f"confirm_payment_{payment_code}_{message.from_user.id}"
            )
            admin_builder.button(
                text="❌ Отклонить",
                callback_data=f"reject_payment_{payment_code}_{message.from_user.id}"
            )
            admin_builder.adjust(1)
            
            admin_text = f"""
📸 <b>Скриншот оплаты</b>

<b>Код платежа:</b> <code>{payment_code}</code>
<b>Пользователь:</b> @{message.from_user.username or 'no_username'}
<b>Сумма:</b> {data['amount']} ₽

Проверьте поступление средств и подтвердите или отклоните платеж.
"""
            
            await bot.send_message(
                admin_id,
                admin_text,
                reply_markup=admin_builder.as_markup(),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to forward payment proof to admin {admin_id}: {e}")
    
    await message.answer(
        "✅ <b>Скриншот получен!</b>\n\n"
        "Ваш платеж проверяется. Обычно это занимает до 5 минут.\n"
        "Вы получите уведомление о результате проверки.",
        parse_mode="HTML"
    )
    await state.clear()

@router.callback_query(F.data.startswith("confirm_payment_"))
async def confirm_payment(callback: types.CallbackQuery):
    """Подтверждение платежа админом"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав для этого действия!", show_alert=True)
        return
    
    parts = callback.data.split("_")
    payment_code = parts[2]
    user_telegram_id = int(parts[3])
    
    db = SessionLocal()
    try:
        # Находим платеж и пользователя
        payment = db.query(Payment).filter(Payment.payment_code == payment_code).first()
        user = db.query(User).filter(User.telegram_id == user_telegram_id).first()
        
        if not payment or not user:
            await callback.answer("Платеж или пользователь не найден!", show_alert=True)
            return
        
        # Активируем подписку
        payment.is_confirmed = True
        user.is_active = True
        
        if user.expires_at and user.expires_at > datetime.now():
            # Продлеваем существующую подписку
            user.expires_at += timedelta(days=payment.days)
        else:
            # Новая подписка
            user.expires_at = datetime.now() + timedelta(days=payment.days)
        
        user.total_paid += payment.amount
        db.commit()
        
        # Добавляем пользователя в Xray
        email = f"{user.username or user.telegram_id}@{SERVER_DOMAIN}"
        await xray_manager.add_user(user.uuid, email)
        
        # Уведомляем пользователя
        success_text = f"""
✅ <b>Платеж подтвержден!</b>

Ваша подписка активирована на {payment.days} дней.
Срок действия до: {user.expires_at.strftime('%d.%m.%Y')}

Теперь вы можете получить конфигурацию VPN.
"""
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📱 Получить конфигурацию", callback_data="get_config")
        builder.button(text="📊 QR-код", callback_data="get_qr")
        builder.adjust(1)
        
        await bot.send_message(
            user_telegram_id,
            success_text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        
        await callback.message.edit_text(
            f"✅ Платеж {payment_code} подтвержден!",
            parse_mode="HTML"
        )
        
        logger.info(f"Payment {payment_code} confirmed for user {user_telegram_id}")
        
    except Exception as e:
        logger.error(f"Error confirming payment: {e}")
        await callback.answer("Ошибка при подтверждении платежа!", show_alert=True)
    finally:
        db.close()

@router.callback_query(F.data.startswith("reject_payment_"))
async def reject_payment(callback: types.CallbackQuery):
    """Отклонение платежа админом"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав для этого действия!", show_alert=True)
        return
    
    parts = callback.data.split("_")
    payment_code = parts[2]
    user_telegram_id = int(parts[3])
    
    await bot.send_message(
        user_telegram_id,
        "❌ <b>Платеж отклонен</b>\n\n"
        "Ваш платеж не был подтвержден. Возможные причины:\n"
        "• Неверная сумма перевода\n"
        "• Не указан код платежа в комментарии\n"
        "• Платеж не поступил\n\n"
        "Пожалуйста, обратитесь в поддержку для выяснения причин.",
        parse_mode="HTML"
    )
    
    await callback.message.edit_text(
        f"❌ Платеж {payment_code} отклонен",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "instructions")
async def instructions(callback: types.CallbackQuery):
    """Инструкции по настройке"""
    text = """
📖 <b>Инструкция по настройке VPN</b>

<b>Android (v2rayNG):</b>
1. Скачайте v2rayNG из Google Play
2. Откройте приложение
3. Нажмите "+" → "Импорт из буфера обмена"
4. Скопируйте VLESS ссылку из бота и вставьте
5. Нажмите на иконку V внизу для подключения

<b>iOS (Shadowrocket):</b>
1. Купите Shadowrocket в App Store
2. Откройте приложение
3. Нажмите "+" в правом верхнем углу
4. Выберите "Type" → VLESS
5. Введите параметры из бота
6. Сохраните и включите VPN

<b>Windows (v2rayN):</b>
1. Скачайте v2rayN с GitHub
2. Запустите программу
3. Правый клик на иконке в трее
4. "Серверы" → "Импорт из буфера обмена"
5. Скопируйте VLESS ссылку и импортируйте

<b>Видео-инструкции:</b>
• Android: youtube.com/watch?v=xxxxx
• iOS: youtube.com/watch?v=xxxxx
• Windows: youtube.com/watch?v=xxxxx

Если возникли проблемы - обратитесь в поддержку!
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="💬 Поддержка", callback_data="support")
    builder.button(text="🔙 Назад", callback_data="my_vpn")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "support")
async def support(callback: types.CallbackQuery):
    """Поддержка"""
    text = """
💬 <b>Служба поддержки</b>

Если у вас возникли вопросы или проблемы, вы можете:

1. 📞 Написать в поддержку: @your_support_username
2. 💬 Вступить в чат пользователей: @your_chat_link
3. 📧 Написать на email: support@yourdomain.com

<b>Часы работы поддержки:</b>
Пн-Пт: 10:00 - 22:00
Сб-Вс: 12:00 - 20:00

<b>Среднее время ответа:</b> 5-15 минут

Мы всегда готовы помочь вам! 😊
"""
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: types.CallbackQuery):
    """Админ-панель"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав доступа!", show_alert=True)
        return
    
    db = SessionLocal()
    try:
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.is_active == True).count()
        total_revenue = db.query(func.sum(Payment.amount)).filter(Payment.is_confirmed == True).scalar() or 0
        
        xray_status = await xray_manager.get_xray_status()
        
        text = f"""
⚙️ <b>Админ-панель</b>

<b>📊 Статистика:</b>
• Всего пользователей: {total_users}
• Активных подписок: {active_users}
• Общий доход: {total_revenue:.2f} ₽

<b>🖥 Статус сервера:</b>
• Xray: {xray_status}
• Сервер: {SERVER_DOMAIN}

<b>Выберите действие:</b>
"""
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📊 Детальная статистика", callback_data="admin_stats")
        builder.button(text="👥 Управление пользователями", callback_data="admin_users")
        builder.button(text="📢 Рассылка", callback_data="admin_broadcast")
        builder.button(text="🔄 Перезапустить Xray", callback_data="admin_restart_xray")
        builder.button(text="💾 Бэкап базы", callback_data="admin_backup")
        builder.button(text="🔙 Назад", callback_data="back_to_main")
        builder.adjust(2, 2, 2)
        
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        
    finally:
        db.close()

@router.callback_query(F.data == "admin_restart_xray")
async def admin_restart_xray(callback: types.CallbackQuery):
    """Перезапуск Xray"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("У вас нет прав доступа!", show_alert=True)
        return
    
    await callback.answer("Перезапускаю Xray...")
    success = await xray_manager.restart_xray()
    
    if success:
        await callback.answer("✅ Xray успешно перезапущен!", show_alert=True)
    else:
        await callback.answer("❌ Ошибка перезапуска Xray!", show_alert=True)

# Фоновые задачи
async def check_expired_subscriptions():
    """Проверка истекших подписок"""
    while True:
        try:
            db = SessionLocal()
            expired_users = db.query(User).filter(
                User.is_active == True,
                User.expires_at < datetime.now()
            ).all()
            
            for user in expired_users:
                # Деактивируем пользователя
                user.is_active = False
                
                # Удаляем из Xray
                await xray_manager.remove_user(user.uuid)
                
                # Уведомляем пользователя
                try:
                    await bot.send_message(
                        user.telegram_id,
                        "⚠️ <b>Ваша подписка истекла!</b>\n\n"
                        "Чтобы продолжить пользоваться VPN, пожалуйста, продлите подписку.",
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to notify user {user.telegram_id} about expiration: {e}")
                
                logger.info(f"Subscription expired for user {user.telegram_id}")
            
            db.commit()
            db.close()
            
        except Exception as e:
            logger.error(f"Error checking expired subscriptions: {e}")
        
        # Проверяем каждый час
        await asyncio.sleep(3600)

async def send_expiration_warnings():
    """Отправка предупреждений об истечении подписки"""
    while True:
        try:
            db = SessionLocal()
            
            # Предупреждаем за 3 дня до истечения
            warning_date = datetime.now() + timedelta(days=3)
            users_to_warn = db.query(User).filter(
                User.is_active == True,
                User.expires_at > datetime.now(),
                User.expires_at < warning_date
            ).all()
            
            for user in users_to_warn:
                days_left = (user.expires_at - datetime.now()).days
                try:
                    builder = InlineKeyboardBuilder()
                    builder.button(text="🔄 Продлить подписку", callback_data="buy_subscription")
                    
                    await bot.send_message(
                        user.telegram_id,
                        f"⏰ <b>Напоминание</b>\n\n"
                        f"Ваша подписка истекает через {days_left} дн.\n"
                        f"Не забудьте продлить её заранее!",
                        reply_markup=builder.as_markup(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to send warning to user {user.telegram_id}: {e}")
            
            db.close()
            
        except Exception as e:
            logger.error(f"Error sending expiration warnings: {e}")
        
        # Проверяем каждые 24 часа
        await asyncio.sleep(86400)

# Запуск бота
async def main():
    """Главная функция"""
    # Регистрируем роутер
    dp.include_router(router)
    
    # Запускаем фоновые задачи
    asyncio.create_task(check_expired_subscriptions())
    asyncio.create_task(send_expiration_warnings())
    
    # Удаляем вебхук и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
