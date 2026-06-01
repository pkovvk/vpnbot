from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from database.models import User, Subscription, Payment, ReferralReward, SubscriptionStatus
from datetime import datetime, timezone
import secrets
import string


def _generate_referral_code(length: int = 8) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(
        self,
        user_id: int,
        username: str | None,
        full_name: str,
        language_code: str | None = None,
        referred_by_code: str | None = None,
    ) -> tuple["User", bool]:
        """Возвращает (user, created)"""
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user:
            # Обновляем данные
            user.username = username
            user.full_name = full_name
            await self.session.commit()
            return user, False

        # Создаём нового пользователя
        ref_code = _generate_referral_code()
        # Убеждаемся что код уникальный
        while True:
            existing = await self.session.execute(
                select(User).where(User.referral_code == ref_code)
            )
            if not existing.scalar_one_or_none():
                break
            ref_code = _generate_referral_code()

        referred_by_id = None
        if referred_by_code:
            ref_result = await self.session.execute(
                select(User).where(User.referral_code == referred_by_code)
            )
            referrer = ref_result.scalar_one_or_none()
            if referrer and referrer.id != user_id:
                referred_by_id = referrer.id

        user = User(
            id=user_id,
            username=username,
            full_name=full_name,
            language_code=language_code,
            referral_code=ref_code,
            referred_by_id=referred_by_id,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user, True

    async def get_by_id(self, user_id: int) -> "User | None":
        result = await self.session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_referral_code(self, code: str) -> "User | None":
        result = await self.session.execute(
            select(User).where(User.referral_code == code)
        )
        return result.scalar_one_or_none()

    async def update_balance(self, user_id: int, delta: float) -> float:
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user:
            user.balance = max(0.0, user.balance + delta)
            await self.session.commit()
            return user.balance
        return 0.0

    async def get_all_active_ids(self) -> list[int]:
        result = await self.session.execute(select(User.id).where(User.is_banned == False))
        return [row[0] for row in result.all()]

    async def get_stats(self) -> dict:
        from sqlalchemy import func, and_
        total = await self.session.execute(select(func.count(User.id)))
        active_subs = await self.session.execute(
            select(func.count(Subscription.id)).where(
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
            )
        )
        total_revenue = await self.session.execute(
            select(func.sum(Payment.amount_paid)).where(
                Payment.status == "completed"
            )
        )
        return {
            "total_users": total.scalar() or 0,
            "active_subscriptions": active_subs.scalar() or 0,
            "total_revenue": total_revenue.scalar() or 0.0,
        }


class SubscriptionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_active(self, user_id: int) -> "Subscription | None":
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.user_id == user_id,
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        started_at: datetime,
        expires_at: datetime,
        status: SubscriptionStatus,
        xui_client_id: str | None = None,
        xui_email: str | None = None,
        xui_inbound_id: int | None = None,
        xui_sub_id: str | None = None,
    ) -> "Subscription":
        sub = Subscription(
            user_id=user_id,
            started_at=started_at,
            expires_at=expires_at,
            status=status,
            xui_client_id=xui_client_id,
            xui_email=xui_email,
            xui_inbound_id=xui_inbound_id,
            xui_sub_id=xui_sub_id,
        )
        self.session.add(sub)
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def update_status(self, sub_id: int, status: SubscriptionStatus):
        await self.session.execute(
            update(Subscription).where(Subscription.id == sub_id).values(status=status)
        )
        await self.session.commit()

    async def get_expiring_soon(self, days: int) -> list["Subscription"]:
        """Подписки, истекающие через `days` дней (±1 час для надёжности)"""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        target = now + timedelta(days=days)
        window_start = target.replace(hour=0, minute=0, second=0, microsecond=0)
        window_end = target.replace(hour=23, minute=59, second=59)

        result = await self.session.execute(
            select(Subscription).where(
                Subscription.expires_at >= window_start,
                Subscription.expires_at <= window_end,
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
                Subscription.notified_3days == False,
            )
        )
        return list(result.scalars().all())

    async def get_expired(self) -> list["Subscription"]:
        now = datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Subscription).where(
                Subscription.expires_at <= now,
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            )
        )
        return list(result.scalars().all())

    async def mark_notified_3days(self, sub_id: int):
        await self.session.execute(
            update(Subscription).where(Subscription.id == sub_id).values(notified_3days=True)
        )
        await self.session.commit()

    async def mark_notified_expired(self, sub_id: int):
        await self.session.execute(
            update(Subscription).where(Subscription.id == sub_id).values(notified_expired=True)
        )
        await self.session.commit()


class PaymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, **kwargs) -> "Payment":
        payment = Payment(**kwargs)
        self.session.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def get_by_provider_id(self, provider_payment_id: str) -> "Payment | None":
        result = await self.session.execute(
            select(Payment).where(Payment.provider_payment_id == provider_payment_id)
        )
        return result.scalar_one_or_none()

    async def complete(self, payment_id: int):
        await self.session.execute(
            update(Payment).where(Payment.id == payment_id).values(
                status="completed",
                completed_at=datetime.now(timezone.utc),
            )
        )
        await self.session.commit()

    async def fail(self, payment_id: int):
        await self.session.execute(
            update(Payment).where(Payment.id == payment_id).values(status="failed")
        )
        await self.session.commit()


class ReferralRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_reward(self, referrer_id: int, referral_id: int, amount: float):
        reward = ReferralReward(
            referrer_id=referrer_id,
            referral_id=referral_id,
            amount_rub=amount,
        )
        self.session.add(reward)
        await self.session.commit()

    async def get_referral_count(self, user_id: int) -> int:
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count(ReferralReward.id)).where(ReferralReward.referrer_id == user_id)
        )
        return result.scalar() or 0
