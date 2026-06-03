from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from config import settings


# ─── Главное меню ────────────────────────────────────────────────────────────

def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="🔑 Мой доступ"))
    kb.row(KeyboardButton(text="💳 Купить подписку"), KeyboardButton(text="👥 Реферальная программа"))
    kb.row(KeyboardButton(text="ℹ️ Помощь"))
    return kb.as_markup(resize_keyboard=True)


# ─── Подписка ─────────────────────────────────────────────────────────────────

def subscription_plans_kb(has_used_trial: bool, has_discount: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if not has_used_trial:
        builder.row(InlineKeyboardButton(
            text="🎁 Пробный период (7 дней — бесплатно)",
            callback_data="plan_trial",
        ))

    discounted = int(settings.PRICE_1_MONTH * (1 - settings.REFERRAL_DISCOUNT_PERCENT / 100))
    price_label = f"1 месяц — {discounted}₽ (скидка {settings.REFERRAL_DISCOUNT_PERCENT}%)" if has_discount else f"1 месяц — {settings.PRICE_1_MONTH}₽"
    builder.row(InlineKeyboardButton(
        text=f"📅 {price_label}",
        callback_data="plan_month",
    ))

    return builder.as_markup()


def payment_method_kb(plan: str, balance: float = 0.0, price: float = 0.0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    if balance > 0:
        if balance >= price:
            builder.row(InlineKeyboardButton(
                text=f"💰 Оплатить с баланса ({balance:.0f}₽) — бесплатно",
                callback_data=f"pay_balance_{plan}",
            ))
        else:
            builder.row(InlineKeyboardButton(
                text=f"💰 Частично балансом ({balance:.0f}₽ из {price:.0f}₽)",
                callback_data=f"pay_balance_{plan}",
            ))

    if settings.YOOKASSA_SHOP_ID and settings.YOOKASSA_SECRET_KEY:
        builder.row(InlineKeyboardButton(text="💳 ЮКасса (карта РФ)", callback_data=f"pay_yookassa_{plan}"))

    if settings.CRYPTOBOT_API_TOKEN:
        builder.row(InlineKeyboardButton(text="₿ Криптовалюта (USDT)", callback_data=f"pay_crypto_{plan}"))

    builder.row(InlineKeyboardButton(text="⭐ Telegram Stars", callback_data=f"pay_stars_{plan}"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_plans"))
    return builder.as_markup()


def payment_url_kb(url: str, payment_id: str, provider: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Перейти к оплате", url=url))
    builder.row(InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_payment_{provider}_{payment_id}"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_payment"))
    return builder.as_markup()


def my_access_kb(has_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_active:
        builder.row(InlineKeyboardButton(text="🔗 Получить ссылку подключения", callback_data="get_link"))
        builder.row(InlineKeyboardButton(text="📖 Инструкция по подключению", callback_data="howto"))
        builder.row(InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="extend_sub"))
    else:
        builder.row(InlineKeyboardButton(text="🛒 Купить подписку", callback_data="go_buy"))
    return builder.as_markup()


def howto_kb(sub_id: str) -> InlineKeyboardMarkup:
    """Клавиатура с одной кнопкой-ссылкой на инструкцию по подключению."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📖 Инструкция по подключению",
        url=f"https://leftvpn.online/sub/?id={sub_id}",
    ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_access"))
    return builder.as_markup()


# ─── Реферальная программа ───────────────────────────────────────────────────

def referral_kb(ref_link: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📤 Поделиться реферальной ссылкой",
        url=f"https://t.me/share/url?url={ref_link}&text=Попробуй%20мой%20VPN%20сервис!",
    ))
    return builder.as_markup()


# ─── Админ панель ─────────────────────────────────────────────────────────────

def admin_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    builder.row(
        InlineKeyboardButton(text="✅ Выдать подписку", callback_data="admin_grant"),
        InlineKeyboardButton(text="❌ Отозвать подписку", callback_data="admin_revoke"),
    )
    builder.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    builder.row(InlineKeyboardButton(text="🔍 Найти пользователя", callback_data="admin_find_user"))
    return builder.as_markup()


def admin_broadcast_type_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📝 Только текст", callback_data="broadcast_text"))
    builder.row(InlineKeyboardButton(text="🖼 Текст + фото", callback_data="broadcast_photo"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel"))
    return builder.as_markup()


def admin_confirm_kb(action: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_{action}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel"),
    )
    return builder.as_markup()