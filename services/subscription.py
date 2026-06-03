"""
Сервис управления подписками.
Связывает БД и 3x-ui: создаёт/отзывает/продлевает подписки.
"""

from datetime import datetime, timezone, timedelta
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import (
    UserRepository, SubscriptionRepository, ReferralRepository,
    SubscriptionStatus,
)
from services.xui import xui_manager

logger = logging.getLogger(__name__)


def _make_xui_email(user_id: int) -> str:
    """Уникальный email для 3x-ui (используется как идентификатор клиента)."""
    return f"user_{user_id}@vpnbot"


async def activate_subscription(
    session: AsyncSession,
    user_id: int,
    plan_days: int,
    is_trial: bool = False,
    payment_id: int | None = None,
) -> tuple[bool, str]:
    """
    Активировать подписку.
    Создаёт/продлевает клиента в 3x-ui и записывает в БД.
    Возвращает (success, sub_link | error_msg).
    """

    sub_repo = SubscriptionRepository(session)
    user_repo = UserRepository(session)

    now = datetime.now(timezone.utc)

    existing = await sub_repo.get_active(user_id)

    if existing and existing.expires_at.replace(tzinfo=timezone.utc) > now:
        base_date = existing.expires_at.replace(tzinfo=timezone.utc)
    else:
        base_date = now

    expires_at = base_date + timedelta(days=plan_days)
    email = _make_xui_email(user_id)

    # ========== ПРОДЛЕНИЕ ==========
    if existing and existing.xui_client_id:
        ok = await xui_manager.update_expiry_all_nodes(
            existing.xui_client_id,
            email,
            expires_at,
        )

        if ok:
            existing.expires_at = expires_at
            existing.status = SubscriptionStatus.ACTIVE
            existing.notified_3days = False
            existing.notified_expired = False
            await session.commit()

            link = await xui_manager.main_node.get_client_link(
                existing.xui_client_id,
                email,
                existing.xui_sub_id or "",
            )
            return True, link or "Подписка продлена"

        return False, "Не удалось продлить в 3x-ui"

    # ========== СОЗДАНИЕ ==========
    total_gb = 20 if is_trial else 200

    ok, client_id, sub_id = await xui_manager.create_client_all_nodes(
        email=email,
        expires_at=expires_at,
        total_gb=total_gb,
        inbound_ids=settings.XUI_INBOUND_IDS,   # <<< ВАЖНО
    )

    if not ok:
        return False, "Не удалось создать клиента в 3x-ui"

    if existing:
        await sub_repo.update_status(existing.id, SubscriptionStatus.EXPIRED)

    status = SubscriptionStatus.TRIAL if is_trial else SubscriptionStatus.ACTIVE

    sub = await sub_repo.create(
        user_id=user_id,
        started_at=now,
        expires_at=expires_at,
        status=status,
        xui_client_id=client_id,
        xui_email=email,
        xui_sub_id=sub_id,
    )

    # ========== ТРИАЛ + РЕФЕРАЛКА ==========
    if is_trial:
        user = await user_repo.get_by_id(user_id)
        if user:
            user.has_used_trial = True
            await session.commit()

            if user.referred_by_id:
                ref_repo = ReferralRepository(session)

                await ref_repo.add_reward(
                    referrer_id=user.referred_by_id,
                    referral_id=user_id,
                    amount=settings.REFERRAL_REWARD_RUB,
                )

                await user_repo.update_balance(
                    user.referred_by_id,
                    settings.REFERRAL_REWARD_RUB,
                )

    link = await xui_manager.main_node.get_client_link(
        client_id,
        email,
        sub_id,
    )

    return True, link or "Подписка активирована"


async def revoke_subscription(
    session: AsyncSession,
    user_id: int,
    reason: str = "expired",
) -> bool:
    """Отозвать подписку (отключить в 3x-ui + пометить в БД)."""

    sub_repo = SubscriptionRepository(session)
    sub = await sub_repo.get_active(user_id)

    if not sub:
        return False

    email = _make_xui_email(user_id)

    if sub.xui_client_id:
        await xui_manager.toggle_client_all_nodes(
            sub.xui_client_id,
            email,
            enable=False,
        )

    status = (
        SubscriptionStatus.SUSPENDED
        if reason == "manual"
        else SubscriptionStatus.EXPIRED
    )

    await sub_repo.update_status(sub.id, status)
    return True


async def restore_subscription(
    session: AsyncSession,
    user_id: int,
) -> bool:
    """Восстановить вручную отозванную подписку."""

    sub_repo = SubscriptionRepository(session)
    sub = await sub_repo.get_active(user_id)

    if not sub:
        return False

    email = _make_xui_email(user_id)

    if sub.xui_client_id:
        ok = await xui_manager.toggle_client_all_nodes(
            sub.xui_client_id,
            email,
            enable=True,
        )

        if ok:
            await sub_repo.update_status(sub.id, SubscriptionStatus.ACTIVE)
            return True

    return False


async def get_sub_link(
    session: AsyncSession,
    user_id: int,
) -> str | None:
    """Получить актуальную ссылку подписки."""

    sub_repo = SubscriptionRepository(session)
    sub = await sub_repo.get_active(user_id)

    if not sub or not sub.xui_client_id:
        return None

    email = _make_xui_email(user_id)

    return await xui_manager.main_node.get_client_link(
        sub.xui_client_id,
        email,
        sub.xui_sub_id or "",
    )