from datetime import timezone
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import subscription_plans_kb, my_access_kb, howto_kb, payment_method_kb
from database import SubscriptionRepository
from database.models import User
from services.subscription import get_sub_link, activate_subscription
from services.payments import get_price_with_discount
from database.models import SubscriptionStatus
from config import settings

router = Router()


# def _get_plan_price(plan: str, db_user: User) -> float:
#     """Вычислить финальную цену с учётом скидки."""
#     base = settings.PRICE_1_MONTH if plan == "month" else 0
#     has_discount = (
#         not db_user.has_used_referral_discount
#         and db_user.referred_by_id is not None
#     )
#     if has_discount and plan == "month":
#         return get_price_with_discount(base, settings.REFERRAL_DISCOUNT_PERCENT)
#     return base


# ─── Мой доступ ──────────────────────────────────────────────────────────────

# @router.message(F.text == "🔑 Мой доступ")
# async def my_access(message: Message, db_user: User, session: AsyncSession):
#     sub_repo = SubscriptionRepository(session)
#     sub = await sub_repo.get_active(db_user.id)
#
#     if sub:
#         expires = sub.expires_at.replace(tzinfo=timezone.utc)
#         from datetime import datetime, timezone as tz
#         now = datetime.now(tz.utc)
#         days_left = (expires - now).days
#
#         status_emoji = "✅" if sub.status == SubscriptionStatus.ACTIVE else "🧪"
#         status_label = "Активна" if sub.status == SubscriptionStatus.ACTIVE else "Пробный период"
#
#         text = (
#             f"{status_emoji} <b>Подписка: {status_label}</b>\n\n"
#             f"📅 Действует до: <b>{expires.strftime('%d.%m.%Y')}</b>\n"
#             f"⏳ Осталось: <b>{days_left} дн.</b>\n"
#             f"📱 Устройств: <b>2</b>"
#         )
#     else:
#         text = (
#             "❌ <b>Активной подписки нет</b>\n\n"
#             "Оформите подписку, чтобы начать пользоваться VPN."
#         )
#
#     await message.answer(
#         text,
#         parse_mode="HTML",
#         reply_markup=my_access_kb(has_active=sub is not None),
#     )


# @router.callback_query(F.data == "back_to_access")
# async def back_to_access(callback: CallbackQuery, db_user: User, session: AsyncSession):
#     await callback.message.delete()
#     await my_access(callback.message, db_user, session)
#     await callback.answer()


# @router.callback_query(F.data == "get_link")
# async def get_link(callback: CallbackQuery, db_user: User, session: AsyncSession):
#     sub_repo = SubscriptionRepository(session)
#     sub = await sub_repo.get_active(db_user.id)
#
#     link = await get_sub_link(session, db_user.id)
#     if link and sub and sub.xui_sub_id:
#         await callback.message.answer(
#             f"🔗 <b>Ваша ссылка для подключения:</b>\n\n"
#             f"<code>{link}</code>\n\n"
#             f"Скопируйте ссылку и вставьте в ваш VPN-клиент.\n"
#             f"Нажмите кнопку «Инструкция», если не знаете как подключиться.",
#             parse_mode="HTML",
#             reply_markup=howto_kb(sub.xui_sub_id),
#         )
#     else:
#         await callback.answer("Не удалось получить ссылку. Обратитесь в поддержку.", show_alert=True)
#     await callback.answer()


# @router.callback_query(F.data == "howto")
# async def howto(callback: CallbackQuery, db_user: User, session: AsyncSession):
#     sub_repo = SubscriptionRepository(session)
#     sub = await sub_repo.get_active(db_user.id)
#
#     if not sub or not sub.xui_sub_id:
#         await callback.answer("Подписка не найдена. Обратитесь в поддержку.", show_alert=True)
#         return
#
#     await callback.message.edit_text(
#         "📖 <b>Инструкция по подключению</b>\n\n"
#         "Нажмите кнопку ниже — откроется пошаговая инструкция для вашего устройства.",
#         parse_mode="HTML",
#         reply_markup=howto_kb(sub.xui_sub_id),
#     )
#     await callback.answer()


# ─── Купить подписку ─────────────────────────────────────────────────────────

# @router.message(F.text == "💳 Купить подписку")
# @router.callback_query(F.data == "go_buy")
# @router.callback_query(F.data == "extend_sub")
# @router.callback_query(F.data == "back_to_plans")
# async def show_plans(event, db_user: User, session: AsyncSession):
#     is_callback = isinstance(event, CallbackQuery)
#     message = event.message if is_callback else event
#
#     kb = subscription_plans_kb(
#         has_used_trial=db_user.has_used_trial,
#         has_discount=not db_user.has_used_referral_discount and db_user.referred_by_id is not None,
#     )
#
#     text = (
#         "🛒 <b>Выберите тариф:</b>\n\n"
#         "🔒 Лимит: 200GB/мес\n"
#         "📱 Устройств: 2\n"
#         "⚡️ Скорость: без ограничений\n"
#         "🚫 Логи: не ведутся"
#     )
#
#     if is_callback:
#         await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
#         await event.answer()
#     else:
#         await message.answer(text, parse_mode="HTML", reply_markup=kb)


# @router.callback_query(F.data == "plan_trial")
# async def plan_trial(callback: CallbackQuery, db_user: User, session: AsyncSession):
#     if db_user.has_used_trial:
#         await callback.answer("Вы уже использовали пробный период.", show_alert=True)
#         return
#
#     ok, link_or_err = await activate_subscription(
#         session=session,
#         user_id=db_user.id,
#         plan_days=7,
#         is_trial=True,
#     )
#
#     if ok:
#         sub_repo = SubscriptionRepository(session)
#         sub = await sub_repo.get_active(db_user.id)
#         kb = howto_kb(sub.xui_sub_id) if sub and sub.xui_sub_id else None
#
#         await callback.message.edit_text(
#             f"🎉 <b>Пробный период активирован на 7 дней!</b>\n\n"
#             f"🔗 <b>Ваша ссылка для подключения:</b>\n"
#             f"<code>{link_or_err}</code>\n\n"
#             f"Нажмите «Инструкция», если не знаете как подключиться.",
#             parse_mode="HTML",
#             reply_markup=kb,
#         )
#     else:
#         await callback.message.edit_text(
#             f"❌ Ошибка активации: {link_or_err}\n\nОбратитесь в поддержку.",
#             parse_mode="HTML",
#         )
#     await callback.answer()


# @router.callback_query(F.data == "plan_month")
# async def plan_month(callback: CallbackQuery, db_user: User):
#     price = _get_plan_price("month", db_user)
#
#     await callback.message.edit_text(
#         "💳 <b>Выберите способ оплаты:</b>",
#         parse_mode="HTML",
#         reply_markup=payment_method_kb(
#             plan="month",
#             balance=db_user.balance,
#             price=price,
#         ),
#     )
#     await callback.answer()


# ─── ВРЕМЕННО ОТКЛЮЧЕНО ──────────────────────────────────────────────────────

@router.message(F.text == "💳 Купить подписку")
async def buy_disabled(message: Message):
    await message.answer("⚠️ Временно недоступно.")