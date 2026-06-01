from datetime import timezone
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import subscription_plans_kb, my_access_kb, howto_kb, payment_method_kb
from database import SubscriptionRepository
from database.models import User
from services.subscription import get_sub_link, activate_subscription
from database.models import SubscriptionStatus

router = Router()


# ─── Мой доступ ──────────────────────────────────────────────────────────────

@router.message(F.text == "🔑 Мой доступ")
async def my_access(message: Message, db_user: User, session: AsyncSession):
    sub_repo = SubscriptionRepository(session)
    sub = await sub_repo.get_active(db_user.id)

    if sub:
        expires = sub.expires_at.replace(tzinfo=timezone.utc)
        from datetime import datetime, timezone as tz
        now = datetime.now(tz.utc)
        days_left = (expires - now).days

        status_emoji = "✅" if sub.status == SubscriptionStatus.ACTIVE else "🧪"
        status_label = "Активна" if sub.status == SubscriptionStatus.ACTIVE else "Пробный период"

        text = (
            f"{status_emoji} <b>Подписка: {status_label}</b>\n\n"
            f"📅 Действует до: <b>{expires.strftime('%d.%m.%Y')}</b>\n"
            f"⏳ Осталось: <b>{days_left} дн.</b>\n"
            f"📱 Устройств: <b>2</b>"
        )
    else:
        text = (
            "❌ <b>Активной подписки нет</b>\n\n"
            "Оформите подписку, чтобы начать пользоваться VPN."
        )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=my_access_kb(has_active=sub is not None),
    )


@router.callback_query(F.data == "back_to_access")
async def back_to_access(callback: CallbackQuery, db_user: User, session: AsyncSession):
    await callback.message.delete()
    await my_access(callback.message, db_user, session)
    await callback.answer()


@router.callback_query(F.data == "get_link")
async def get_link(callback: CallbackQuery, db_user: User, session: AsyncSession):
    link = await get_sub_link(session, db_user.id)
    if link:
        await callback.message.answer(
            f"🔗 <b>Ваша ссылка для подключения:</b>\n\n"
            f"<code>{link}</code>\n\n"
            f"Скопируйте ссылку и вставьте в ваш VPN-клиент.\n"
            f"Нажмите кнопку «Инструкция», если не знаете как подключиться.",
            parse_mode="HTML",
            reply_markup=howto_kb(),
        )
    else:
        await callback.answer("Не удалось получить ссылку. Обратитесь в поддержку.", show_alert=True)
    await callback.answer()


@router.callback_query(F.data == "howto")
async def howto(callback: CallbackQuery):
    await callback.message.edit_text(
        "📖 <b>Выберите ваше устройство:</b>",
        parse_mode="HTML",
        reply_markup=howto_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "howto_ios")
async def howto_ios(callback: CallbackQuery):
    await callback.message.edit_text(
        "📱 <b>Подключение на iOS</b>\n\n"
        "1. Установите приложение <b>Happ</b> из App Store\n"
        "2. Откройте бот и нажмите «Получить ссылку подключения»\n"
        "3. Скопируйте ссылку\n"
        "4. В Happ нажмите «+» → «Импорт из буфера обмена»\n"
        "5. Нажмите кнопку подключения ✅",
        parse_mode="HTML",
        reply_markup=howto_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "howto_android")
async def howto_android(callback: CallbackQuery):
    await callback.message.edit_text(
        "🤖 <b>Подключение на Android</b>\n\n"
        "1. Установите <b>v2rayNG</b> из Google Play\n"
        "2. Получите ссылку в боте\n"
        "3. В v2rayNG нажмите «+» → «Импорт конфигурации из буфера обмена»\n"
        "4. Выберите добавленный сервер и нажмите ▶️",
        parse_mode="HTML",
        reply_markup=howto_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "howto_desktop")
async def howto_desktop(callback: CallbackQuery):
    await callback.message.edit_text(
        "💻 <b>Подключение на Windows / Mac</b>\n\n"
        "1. Скачайте <b>Happ</b> с сайта happ.su\n"
        "2. Получите ссылку в боте\n"
        "3. В Happ нажмите «+» → вставьте ссылку\n"
        "4. Нажмите «Подключиться»",
        parse_mode="HTML",
        reply_markup=howto_kb(),
    )
    await callback.answer()


# ─── Купить подписку ─────────────────────────────────────────────────────────

@router.message(F.text == "💳 Купить подписку")
@router.callback_query(F.data == "go_buy")
@router.callback_query(F.data == "extend_sub")
@router.callback_query(F.data == "back_to_plans")
async def show_plans(event, db_user: User, session: AsyncSession):
    is_callback = isinstance(event, CallbackQuery)
    message = event.message if is_callback else event

    kb = subscription_plans_kb(
        has_used_trial=db_user.has_used_trial,
        has_discount=not db_user.has_used_referral_discount and db_user.referred_by_id is not None,
    )

    text = (
        "🛒 <b>Выберите тариф:</b>\n\n"
        "🔒 Лимит: 100GB/мес\n"
        "📱 Устройств: 2\n"
        "⚡️ Скорость: без ограничений\n"
        "🚫 Логи: не ведутся"
    )

    if is_callback:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await event.answer()
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "plan_trial")
async def plan_trial(callback: CallbackQuery, db_user: User, session: AsyncSession):
    if db_user.has_used_trial:
        await callback.answer("Вы уже использовали пробный период.", show_alert=True)
        return

    # Активируем сразу без оплаты
    ok, link_or_err = await activate_subscription(
        session=session,
        user_id=db_user.id,
        plan_days=7,
        is_trial=True,
    )

    if ok:
        await callback.message.edit_text(
            f"🎉 <b>Пробный период активирован на 7 дней!</b>\n\n"
            f"🔗 <b>Ваша ссылка для подключения:</b>\n"
            f"<code>{link_or_err}</code>\n\n"
            f"Нажмите «🔑 Мой доступ» чтобы посмотреть инструкцию по подключению.",
            parse_mode="HTML",
        )
    else:
        await callback.message.edit_text(
            f"❌ Ошибка активации: {link_or_err}\n\nОбратитесь в поддержку.",
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "plan_month")
async def plan_month(callback: CallbackQuery, db_user: User):
    await callback.message.edit_text(
        "💳 <b>Выберите способ оплаты:</b>",
        parse_mode="HTML",
        reply_markup=payment_method_kb("month"),
    )
    await callback.answer()
