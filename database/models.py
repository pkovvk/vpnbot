from sqlalchemy import (
    BigInteger, String, Integer, Float, Boolean,
    DateTime, ForeignKey, Enum as SAEnum, Text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum


class Base(DeclarativeBase):
    pass


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    TRIAL = "trial"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProvider(str, enum.Enum):
    YOOKASSA = "yookassa"
    CRYPTOBOT = "cryptobot"
    TELEGRAM_STARS = "telegram_stars"
    MANUAL = "manual"  # Ручная выдача админом
    REFERRAL_BALANCE = "referral_balance"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # Telegram user_id
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(256))
    language_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    # Реферальная система
    referral_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    referred_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    # Баланс (в рублях, для реферальных бонусов)
    balance: Mapped[float] = mapped_column(Float, default=0.0)

    # Флаги
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    has_used_trial: Mapped[bool] = mapped_column(Boolean, default=False)
    has_used_referral_discount: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user", lazy="selectin")
    payments: Mapped[list["Payment"]] = relationship(back_populates="user", lazy="selectin")
    referred_by: Mapped["User | None"] = relationship(foreign_keys=[referred_by_id], remote_side="User.id")
    referrals: Mapped[list["User"]] = relationship(foreign_keys=[referred_by_id])


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)

    # 3x-ui данные
    xui_client_id: Mapped[str | None] = mapped_column(String(64), nullable=True)   # UUID клиента в 3x-ui
    xui_email: Mapped[str | None] = mapped_column(String(128), nullable=True)       # email (уникальный ключ в 3x-ui)
    xui_inbound_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Подписка
    status: Mapped[SubscriptionStatus] = mapped_column(SAEnum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # Уведомления
    notified_3days: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_expired: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="subscriptions")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)

    provider: Mapped[PaymentProvider] = mapped_column(SAEnum(PaymentProvider))
    provider_payment_id: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)

    amount_rub: Mapped[float] = mapped_column(Float)       # Сумма в рублях
    amount_paid: Mapped[float] = mapped_column(Float)      # Фактически заплаченная сумма (может отличаться при скидке)
    currency: Mapped[str] = mapped_column(String(8), default="RUB")

    status: Mapped[PaymentStatus] = mapped_column(SAEnum(PaymentStatus), default=PaymentStatus.PENDING)

    # Что куплено
    plan_days: Mapped[int] = mapped_column(Integer)  # 7 (trial) или 30 (месяц)
    discount_applied: Mapped[float] = mapped_column(Float, default=0.0)  # % скидки

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="payments")


class ReferralReward(Base):
    """Журнал реферальных начислений"""
    __tablename__ = "referral_rewards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    referral_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    amount_rub: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
