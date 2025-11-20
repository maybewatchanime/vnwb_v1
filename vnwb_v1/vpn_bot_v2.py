#!/usr/bin/env python3
import os
import json
import uuid
import asyncio
import logging
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Dict
import aiofiles
import qrcode
from io import BytesIO
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# ===== КОНФИГУРАЦИЯ =====
BOT_TOKEN = "YOUR_BOT_TOKEN"
ADMIN_IDS = [123456789]
SERVER_DOMAIN = "your.domain.com"
SERVER_PORT = 443
XRAY_CONFIG_PATH = "/usr/local/etc/xray/config.json"
DATABASE_PATH = "/home/universal/vpn_bot/database.json"
LOGS_PATH = "/home/universal/vpn_bot/bot.log"
TRIAL_DAYS = 3
SUBSCRIPTION_PRICE = 500
PAYMENT_CARD = "1234 5678 9012 3456"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOGS_PATH), logging.StreamHandler()]
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
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    return json.load(f)
            except:
                return {"users": {}, "configs": {}, "payments": {}}
        return {"users": {}, "configs": {}, "payments": {}}

    async def save(self):
        async with aiofiles.open(self.path, 'w') as f:
            await f.write(json.dumps(self.data, indent=2, ensure_ascii=False))

    def get_user(self, user_id: str) -> Optional[Dict]:
        return self.data["users"].get(str(user_id))

    async def add_user(self, user_id: int, username: str = None) -> Dict:
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

# ===== ИНИЦИАЛИЗАЦИЯ =====
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
db = Database(DATABASE_PATH)

# ===== КЛАВИАТУРЫ =====
def get_main_keyboard(is_admin: bool = False):
    buttons = [
        [InlineKeyboardButton(text="🔑 Получить ключ", callback_data="get_key")],
        [InlineKeyboardButton(text="📊 Мой статус", callback_data="status")],
        [InlineKeyboardButton(text="💳 Продлить подписку", callback_data="payment")],
        [InlineKeyboardButton(text="📖 Инструкция", callback_data="help")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton(text="👨‍💼 Админ панель", callback_data="admin")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_payment_keyboard():
    buttons = [
        [InlineKeyboardButton(text="💳 Оплатил", callback_data="paid")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ===== ОБРАБОТЧИКИ КОМАНД =====
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    await db.add_user(user_id, username)
    is_admin = user_id in ADMIN_IDS
    welcome_text = f"🚀 Добро пожаловать!\nСтоимость подписки: {SUBSCRIPTION_PRICE}₽/мес"
    await message.answer(welcome_text, reply_markup=get_main_keyboard(is_admin))

# ===== CALLBACK HANDLERS =====
@dp.callback_query_handler(lambda c: c.data == "get_key")
async def get_key_handler(callback: types.CallbackQuery):
    await callback.answer("Функция выдачи ключа будет здесь")

@dp.callback_query_handler(lambda c: c.data == "status")
async def status_handler(callback: types.CallbackQuery):
    await callback.answer("Статус пользователя")

@dp.callback_query_handler(lambda c: c.data == "payment")
async def payment_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_payment.state)
    await callback.message.edit_text(f"💳 Оплата: {SUBSCRIPTION_PRICE}₽", reply_markup=get_payment_keyboard())
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "paid")
async def paid_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await callback.message.edit_text("✅ Оплата подтверждена")
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data == "cancel")
async def cancel_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.finish()
    await callback.message.edit_text("❌ Действие отменено", reply_markup=get_main_keyboard(callback.from_user.id in ADMIN_IDS))
    await callback.answer()

# ===== ФОН =====
async def check_subscriptions():
    while True:
        await asyncio.sleep(3600)  # Пример фоновой задачи

# ===== ЗАПУСК =====
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(check_subscriptions())
    executor.start_polling(dp, skip_updates=True)