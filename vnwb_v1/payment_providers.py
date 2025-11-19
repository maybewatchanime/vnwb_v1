"""
Модуль интеграции платежных систем
Поддерживает: YooMoney, QIWI, CryptoBot
"""

import hashlib
import hmac
import json
import aiohttp
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class PaymentProvider:
    """Базовый класс для платежных провайдеров"""
    
    async def create_invoice(self, amount: float, order_id: str, description: str) -> Dict[str, Any]:
        """Создать счет на оплату"""
        raise NotImplementedError
    
    async def check_payment(self, payment_id: str) -> bool:
        """Проверить статус платежа"""
        raise NotImplementedError
    
    def verify_signature(self, data: Dict[str, Any], signature: str) -> bool:
        """Проверить подпись webhook"""
        raise NotImplementedError


class YooMoneyProvider(PaymentProvider):
    """Интеграция с YooMoney (бывшие Яндекс.Деньги)"""
    
    def __init__(self, wallet_id: str, secret_key: str):
        self.wallet_id = wallet_id
        self.secret_key = secret_key
        self.api_url = "https://yoomoney.ru/api"
        
    async def create_invoice(self, amount: float, order_id: str, description: str) -> Dict[str, Any]:
        """Создать счет через YooMoney"""
        
        # Формируем форму оплаты
        payment_url = (
            f"https://yoomoney.ru/quickpay/confirm?"
            f"receiver={self.wallet_id}&"
            f"quickpay-form=button&"
            f"sum={amount}&"
            f"label={order_id}&"
            f"comment={description}&"
            f"successURL=tg://resolve?domain=your_bot"
        )
        
        return {
            "success": True,
            "payment_url": payment_url,
            "payment_id": order_id
        }
    
    async def check_payment(self, payment_id: str) -> bool:
        """Проверить платеж через API"""
        # Здесь должна быть реализация проверки через YooMoney API
        # Требует OAuth токен
        return False
    
    def verify_signature(self, data: Dict[str, Any], signature: str) -> bool:
        """Проверить подпись от YooMoney"""
        # Формируем строку для проверки подписи
        params = [
            data.get('notification_type'),
            data.get('operation_id'),
            data.get('amount'),
            data.get('currency'),
            data.get('datetime'),
            data.get('sender'),
            data.get('codepro'),
            self.secret_key,
            data.get('label')
        ]
        
        # Убираем None значения
        params = [str(p) for p in params if p is not None]
        params_string = '&'.join(params)
        
        # Вычисляем SHA1 хэш
        calculated_hash = hashlib.sha1(params_string.encode()).hexdigest()
        
        return calculated_hash == signature


class QiwiProvider(PaymentProvider):
    """Интеграция с QIWI"""
    
    def __init__(self, api_key: str, wallet: str):
        self.api_key = api_key
        self.wallet = wallet
        self.api_url = "https://edge.qiwi.com"
        
    async def create_invoice(self, amount: float, order_id: str, description: str) -> Dict[str, Any]:
        """Создать счет через QIWI P2P API"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "amount": {
                "currency": "RUB",
                "value": amount
            },
            "comment": description,
            "expirationDateTime": datetime.now().isoformat(),
            "customFields": {
                "order_id": order_id
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/payin/v2/sites/bills/{order_id}",
                headers=headers,
                json=data
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    return {
                        "success": True,
                        "payment_url": result.get("payUrl"),
                        "payment_id": order_id
                    }
                else:
                    return {
                        "success": False,
                        "error": await response.text()
                    }
    
    async def check_payment(self, payment_id: str) -> bool:
        """Проверить статус платежа QIWI"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_url}/payin/v2/sites/bills/{payment_id}",
                headers=headers
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    return result.get("status", {}).get("value") == "PAID"
                
                return False
    
    def verify_signature(self, data: Dict[str, Any], signature: str) -> bool:
        """Проверить подпись QIWI webhook"""
        # QIWI использует HMAC-SHA256
        invoice_parameters = f"{data.get('amount')}|{data.get('billId')}|{data.get('siteId')}|{data.get('status')}"
        calculated_hash = hmac.new(
            self.api_key.encode(),
            invoice_parameters.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return calculated_hash == signature


class CryptoBotProvider(PaymentProvider):
    """Интеграция с CryptoBot для криптовалютных платежей"""
    
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.api_url = "https://pay.crypt.bot/api"
        
    async def create_invoice(self, amount: float, order_id: str, description: str) -> Dict[str, Any]:
        """Создать криптовалютный счет"""
        
        headers = {
            "Crypto-Pay-API-Token": self.api_token
        }
        
        data = {
            "amount": amount,
            "currency": "USDT",  # Можно изменить на BTC, ETH, и т.д.
            "description": description,
            "payload": order_id
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.api_url}/createInvoice",
                headers=headers,
                json=data
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    
                    if result.get("ok"):
                        invoice = result.get("result", {})
                        return {
                            "success": True,
                            "payment_url": invoice.get("bot_invoice_url"),
                            "payment_id": invoice.get("invoice_id")
                        }
                
                return {
                    "success": False,
                    "error": "Failed to create invoice"
                }
    
    async def check_payment(self, payment_id: str) -> bool:
        """Проверить статус криптоплатежа"""
        
        headers = {
            "Crypto-Pay-API-Token": self.api_token
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.api_url}/getInvoices",
                headers=headers,
                params={"invoice_ids": payment_id}
            ) as response:
                
                if response.status == 200:
                    result = await response.json()
                    
                    if result.get("ok"):
                        invoices = result.get("result", {}).get("items", [])
                        if invoices:
                            return invoices[0].get("status") == "paid"
                
                return False
    
    def verify_signature(self, data: Dict[str, Any], signature: str) -> bool:
        """Проверить подпись CryptoBot webhook"""
        # CryptoBot использует HMAC-SHA256
        check_string = json.dumps(data, separators=(',', ':'))
        
        secret = hashlib.sha256(self.api_token.encode()).digest()
        calculated_hash = hmac.new(
            secret,
            check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return calculated_hash == signature


class PaymentManager:
    """Менеджер для управления различными платежными системами"""
    
    def __init__(self):
        self.providers = {}
        
    def add_provider(self, name: str, provider: PaymentProvider):
        """Добавить платежного провайдера"""
        self.providers[name] = provider
        
    async def create_invoice(
        self, 
        provider_name: str, 
        amount: float, 
        order_id: str, 
        description: str
    ) -> Dict[str, Any]:
        """Создать счет через указанного провайдера"""
        
        if provider_name not in self.providers:
            return {
                "success": False,
                "error": f"Provider {provider_name} not found"
            }
        
        try:
            return await self.providers[provider_name].create_invoice(
                amount, order_id, description
            )
        except Exception as e:
            logger.error(f"Error creating invoice with {provider_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def check_payment(self, provider_name: str, payment_id: str) -> bool:
        """Проверить платеж через провайдера"""
        
        if provider_name not in self.providers:
            return False
        
        try:
            return await self.providers[provider_name].check_payment(payment_id)
        except Exception as e:
            logger.error(f"Error checking payment with {provider_name}: {e}")
            return False
    
    def verify_webhook(
        self, 
        provider_name: str, 
        data: Dict[str, Any], 
        signature: str
    ) -> bool:
        """Проверить webhook от платежной системы"""
        
        if provider_name not in self.providers:
            return False
        
        try:
            return self.providers[provider_name].verify_signature(data, signature)
        except Exception as e:
            logger.error(f"Error verifying webhook from {provider_name}: {e}")
            return False


# Пример использования:
"""
# В основном боте:
from payment_providers import PaymentManager, YooMoneyProvider, QiwiProvider, CryptoBotProvider

# Инициализация
payment_manager = PaymentManager()

# Добавление провайдеров (если есть ключи API)
if YOOMONEY_WALLET and YOOMONEY_SECRET:
    payment_manager.add_provider(
        "yoomoney", 
        YooMoneyProvider(YOOMONEY_WALLET, YOOMONEY_SECRET)
    )

if QIWI_API_KEY and QIWI_WALLET:
    payment_manager.add_provider(
        "qiwi",
        QiwiProvider(QIWI_API_KEY, QIWI_WALLET)
    )

if CRYPTOBOT_TOKEN:
    payment_manager.add_provider(
        "crypto",
        CryptoBotProvider(CRYPTOBOT_TOKEN)
    )

# Создание счета
invoice = await payment_manager.create_invoice(
    "qiwi",  # или "yoomoney", "crypto"
    amount=500,
    order_id="ORDER123",
    description="VPN подписка на 1 месяц"
)

if invoice["success"]:
    payment_url = invoice["payment_url"]
    # Отправить пользователю ссылку на оплату

# Проверка платежа
is_paid = await payment_manager.check_payment("qiwi", "ORDER123")
if is_paid:
    # Активировать подписку
"""
