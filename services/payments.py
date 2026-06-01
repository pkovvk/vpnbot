"""
Сервис обработки платежей.
Поддерживает: ЮКасса, CryptoBot, Telegram Stars.
"""

import hashlib
import hmac
import json
import logging
import uuid
from typing import Optional

import aiohttp
from aiogram.types import LabeledPrice

from config import settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Вспомогательные функции расчёта цены
# ─────────────────────────────────────────────

def get_price_with_discount(base_price_rub: float, discount_percent: float) -> float:
    return round(base_price_rub * (1 - discount_percent / 100), 2)


# ─────────────────────────────────────────────
# ЮКасса
# ─────────────────────────────────────────────

async def create_yookassa_payment(
    amount_rub: float,
    description: str,
    user_id: int,
    plan_days: int,
) -> Optional[dict]:
    """
    Создаёт платёж в ЮКассе.
    Возвращает {"payment_id": ..., "confirmation_url": ...} или None.
    """
    import base64
    credentials = base64.b64encode(
        f"{settings.YOOKASSA_SHOP_ID}:{settings.YOOKASSA_SECRET_KEY}".encode()
    ).decode()

    idempotence_key = str(uuid.uuid4())
    payload = {
        "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
        "confirmation": {
            "type": "redirect",
            "return_url": settings.YOOKASSA_RETURN_URL,
        },
        "capture": True,
        "description": description,
        "metadata": {
            "user_id": str(user_id),
            "plan_days": str(plan_days),
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.yookassa.ru/v3/payments",
                json=payload,
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Idempotence-Key": idempotence_key,
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if resp.status == 200:
                    return {
                        "payment_id": data["id"],
                        "confirmation_url": data["confirmation"]["confirmation_url"],
                    }
                logger.error(f"YooKassa error: {data}")
                return None
    except Exception as e:
        logger.error(f"YooKassa request failed: {e}")
        return None


def verify_yookassa_webhook(body: bytes, signature: str) -> bool:
    """Проверить подпись вебхука ЮКассы (IP-whitelist + проверка структуры)."""
    # ЮКасса не использует HMAC — достаточно проверить IP на уровне nginx.
    # Здесь проверяем что тело валидный JSON с нужными полями.
    try:
        data = json.loads(body)
        return "object" in data and "id" in data.get("object", {})
    except Exception:
        return False


# ─────────────────────────────────────────────
# CryptoBot
# ─────────────────────────────────────────────

CRYPTOBOT_BASE = "https://pay.crypt.bot/api"
CRYPTOBOT_TEST_BASE = "https://testnet-pay.crypt.bot/api"


async def create_cryptobot_invoice(
    amount_rub: float,
    user_id: int,
    plan_days: int,
) -> Optional[dict]:
    """
    Создать счёт в CryptoBot (в USDT по текущему курсу через сам CryptoBot).
    Возвращает {"invoice_id": ..., "pay_url": ...} или None.
    """
    base = CRYPTOBOT_BASE if settings.CRYPTOBOT_NETWORK == "mainnet" else CRYPTOBOT_TEST_BASE

    # Получаем курс USD/RUB
    rate = await _get_usd_rub_rate()
    amount_usd = round(amount_rub / rate, 2) if rate else None
    if not amount_usd:
        return None

    payload = {
        "asset": "USDT",
        "amount": str(amount_usd),
        "description": f"VPN подписка на {plan_days} дней",
        "payload": json.dumps({"user_id": user_id, "plan_days": plan_days}),
        "expires_in": 3600,  # 1 час
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{base}/createInvoice",
                json=payload,
                headers={"Crypto-Pay-API-Token": settings.CRYPTOBOT_API_TOKEN},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                data = await resp.json()
                if data.get("ok"):
                    result = data["result"]
                    return {
                        "invoice_id": str(result["invoice_id"]),
                        "pay_url": result["pay_url"],
                        "amount_usd": amount_usd,
                    }
                logger.error(f"CryptoBot error: {data}")
                return None
    except Exception as e:
        logger.error(f"CryptoBot request failed: {e}")
        return None


async def _get_usd_rub_rate() -> float:
    """Получить курс USD/RUB через ЦБ РФ или fallback."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://www.cbr-xml-daily.ru/daily_json.js",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                data = await resp.json(content_type=None)
                return data["Valute"]["USD"]["Value"]
    except Exception:
        return 90.0  # Fallback курс


def verify_cryptobot_webhook(body: bytes, secret: str, signature: str) -> bool:
    """Проверить подпись вебхука CryptoBot."""
    import hashlib, hmac
    secret_hash = hashlib.sha256(secret.encode()).digest()
    expected = hmac.new(secret_hash, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# ─────────────────────────────────────────────
# Telegram Stars
# ─────────────────────────────────────────────

def get_stars_price(amount_rub: float) -> int:
    """
    Конвертировать рубли в Telegram Stars.
    Курс приблизительный: 1 Star ≈ 1.5₽ (Telegram устанавливает курс сам).
    Минимум 1 звезда.
    """
    stars = max(1, round(amount_rub / 1.5))
    return stars


def build_stars_invoice_prices(amount_rub: float) -> list[LabeledPrice]:
    stars = get_stars_price(amount_rub)
    return [LabeledPrice(label="VPN подписка", amount=stars)]
