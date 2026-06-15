"""
Планировщик задач.
Запускается в фоне и проверяет истекающие/истёкшие подписки.
"""

import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot

from config import settings
from database import AsyncSessionLocal, SubscriptionRepository, SubscriptionStatus
from services.subscription import revoke_subscription

logger = logging.getLogger(__name__)


async def check_expiring_subscriptions(bot: Bot):
    """Уведомить пользователей, чья подписка истекает через N дней."""
    async with AsyncSessionLocal() as session:
        sub_repo = SubscriptionRepository(session)
        subs = await sub_repo.get_expiring_soon(settings.NOTIFY_BEFORE_DAYS)

        for sub in subs:
            try:
                days_left = (sub.expires_at.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)).days + 1
                await bot.send_message(
                    sub.user_id,
                    f"⚠️ <b>Ваша подписка истекает через {days_left} дня(-ей)!</b>\n\n"
                    f"📅 Дата окончания: {sub.expires_at.strftime('%d.%m.%Y %H:%M')} UTC\n\n"
                    f"Чтобы не потерять доступ — продлите подписку в главном меню.",
                    parse_mode="HTML",
                )
                await sub_repo.mark_notified_3days(sub.id)
            except Exception as e:
                logger.warning(f"Could not notify user {sub.user_id}: {e}")


async def check_expired_subscriptions(bot: Bot):
    """Отозвать истёкшие подписки и уведомить пользователей."""
    async with AsyncSessionLocal() as session:
        sub_repo = SubscriptionRepository(session)
        subs = await sub_repo.get_expired()

        for sub in subs:
            try:
                # await revoke_subscription(session, sub.user_id, reason="expired")
                await sub_repo.mark_notified_expired(sub.id)

                await bot.send_message(
                    sub.user_id,
                    "❌ <b>Ваша подписка истекла.</b>\n\n"
                    "Доступ к VPN приостановлен. Вы можете продлить подписку "
                    "через главное меню — и мы сразу восстановим ваш доступ! 🔄",
                    parse_mode="HTML",
                )
            except Exception as e:
                logger.warning(f"Could not process expiry for user {sub.user_id}: {e}")


async def scheduler_loop(bot: Bot):
    """Основной цикл планировщика. Запускается каждый час."""
    logger.info("Scheduler started")
    while True:
        try:
            await check_expiring_subscriptions(bot)
            await check_expired_subscriptions(bot)
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)

        await asyncio.sleep(3600)  # Проверка раз в час
