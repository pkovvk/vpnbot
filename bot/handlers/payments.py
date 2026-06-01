from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import payment_url_kb
from config import settings
from database import PaymentRepository, SubscriptionRepository
from database.models import User, PaymentProvider, PaymentStatus
from services.payments import (
    create_yookassa_payment,
    create_cryptobot_invoice,
    get_stars_price,
    get_price_with_discount,
)
from services.subscription import activate_subscription

router = Router()

PLAN_DAYS = {"month": 30, "trial": 7}


def _get_price(plan: str, db_user: User) -> float:
    base = settings.PRICE_1_MONTH if plan == "month" else 0
    has_discount = (
        not db_user.has_used_referral_discount
        and db_user.referred_by_id is not None
    )
    if has_discount and plan == "month":
        return get_price_with_discount(base, settings.REFERRAL_DISCOUNT_PERCENT)
    return base


# ─── ЮКасса ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pay_yookassa_"))
async def pay_yookassa(callback: CallbackQuery, db_user: User, session: AsyncSession):
    plan = callback.data.split("_")[-1]
    price = _get_price(plan, db_user)
    days = PLAN_DAYS[plan]

    await callback.message.edit_text("⏳ Создаём платёж...", parse_mode="HTML")

    result = await create_yookassa_payment(
        amount_rub=price,
        description=f"VPN на {days} дней",
        user_id=db_user.id,
        plan_days=days,
    )

    if not result:
        await callback.message.edit_text("❌ Ошибка создания платежа. Попробуйте позже.")
        await callback.answer()
        return

    pay_repo = PaymentRepository(session)
    has_discount = not db_user.has_used_referral_discount and db_user.referred_by_id is not None
    payment = await pay_repo.create(
        user_id=db_user.id,
        provider=PaymentProvider.YOOKASSA,
        provider_payment_id=result["payment_id"],
        amount_rub=settings.PRICE_1_MONTH if plan == "month" else 0,
        amount_paid=price,
        plan_days=days,
        discount_applied=settings.REFERRAL_DISCOUNT_PERCENT if has_discount else 0,
    )

    await callback.message.edit_text(
        f"💳 <b>Оплата через ЮКассу</b>\n\n"
        f"Сумма: <b>{price:.0f}₽</b>\n"
        f"Подписка: <b>{days} дней</b>\n\n"
        f"После оплаты нажмите «✅ Я оплатил»",
        parse_mode="HTML",
        reply_markup=payment_url_kb(
            result["confirmation_url"],
            result["payment_id"],
            "yookassa",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check_payment_yookassa_"))
async def check_yookassa(callback: CallbackQuery, db_user: User, session: AsyncSession):
    payment_id = callback.data.replace("check_payment_yookassa_", "")

    pay_repo = PaymentRepository(session)
    payment = await pay_repo.get_by_provider_id(payment_id)

    if not payment or payment.user_id != db_user.id:
        await callback.answer("Платёж не найден.", show_alert=True)
        return

    if payment.status == PaymentStatus.COMPLETED:
        await callback.answer("✅ Подписка уже активирована!", show_alert=True)
        return

    # Проверяем статус через API ЮКассы
    import base64, aiohttp
    credentials = base64.b64encode(
        f"{settings.YOOKASSA_SHOP_ID}:{settings.YOOKASSA_SECRET_KEY}".encode()
    ).decode()

    await callback.answer("Проверяем платёж...", show_alert=False)

    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(
                f"https://api.yookassa.ru/v3/payments/{payment_id}",
                headers={"Authorization": f"Basic {credentials}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
    except Exception:
        await callback.answer("Ошибка проверки. Попробуйте чуть позже.", show_alert=True)
        return

    if data.get("status") == "succeeded":
        await pay_repo.complete(payment.id)

        # Помечаем скидку использованной
        if payment.discount_applied > 0:
            db_user.has_used_referral_discount = True
            await session.commit()

        ok, link_or_err = await activate_subscription(
            session=session,
            user_id=db_user.id,
            plan_days=payment.plan_days,
        )

        if ok:
            await callback.message.edit_text(
                f"✅ <b>Оплата прошла! Подписка активирована.</b>\n\n"
                f"🔗 Ссылка для подключения:\n<code>{link_or_err}</code>",
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(
                "✅ Оплата получена, но возникла ошибка активации. "
                "Обратитесь в поддержку — мы активируем вручную.",
                parse_mode="HTML",
            )
    elif data.get("status") in ("pending", "waiting_for_capture"):
        await callback.answer("Платёж ещё не поступил. Подождите и попробуйте снова.", show_alert=True)
    else:
        await pay_repo.fail(payment.id)
        await callback.answer("Платёж не прошёл.", show_alert=True)


# ─── CryptoBot ───────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pay_crypto_"))
async def pay_crypto(callback: CallbackQuery, db_user: User, session: AsyncSession):
    plan = callback.data.split("_")[-1]
    price = _get_price(plan, db_user)
    days = PLAN_DAYS[plan]

    await callback.message.edit_text("⏳ Создаём счёт в крипте...")

    result = await create_cryptobot_invoice(
        amount_rub=price,
        user_id=db_user.id,
        plan_days=days,
    )

    if not result:
        await callback.message.edit_text("❌ Ошибка создания счёта. Попробуйте позже.")
        await callback.answer()
        return

    pay_repo = PaymentRepository(session)
    has_discount = not db_user.has_used_referral_discount and db_user.referred_by_id is not None
    payment = await pay_repo.create(
        user_id=db_user.id,
        provider=PaymentProvider.CRYPTOBOT,
        provider_payment_id=result["invoice_id"],
        amount_rub=settings.PRICE_1_MONTH if plan == "month" else 0,
        amount_paid=price,
        currency="USDT",
        plan_days=days,
        discount_applied=settings.REFERRAL_DISCOUNT_PERCENT if has_discount else 0,
    )

    await callback.message.edit_text(
        f"₿ <b>Оплата криптовалютой</b>\n\n"
        f"Сумма: <b>{result['amount_usd']} USDT</b> (~{price:.0f}₽)\n"
        f"Подписка: <b>{days} дней</b>\n\n"
        f"После оплаты нажмите «✅ Я оплатил»",
        parse_mode="HTML",
        reply_markup=payment_url_kb(
            result["pay_url"],
            result["invoice_id"],
            "crypto",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("check_payment_crypto_"))
async def check_crypto(callback: CallbackQuery, db_user: User, session: AsyncSession):
    invoice_id = callback.data.replace("check_payment_crypto_", "")

    pay_repo = PaymentRepository(session)
    payment = await pay_repo.get_by_provider_id(invoice_id)

    if not payment or payment.user_id != db_user.id:
        await callback.answer("Платёж не найден.", show_alert=True)
        return

    if payment.status == PaymentStatus.COMPLETED:
        await callback.answer("✅ Подписка уже активирована!", show_alert=True)
        return

    import aiohttp
    from config import settings as cfg

    base = "https://pay.crypt.bot/api" if cfg.CRYPTOBOT_NETWORK == "mainnet" else "https://testnet-pay.crypt.bot/api"
    try:
        async with aiohttp.ClientSession() as http:
            async with http.get(
                f"{base}/getInvoices",
                params={"invoice_ids": invoice_id},
                headers={"Crypto-Pay-API-Token": cfg.CRYPTOBOT_API_TOKEN},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
    except Exception:
        await callback.answer("Ошибка проверки. Попробуйте позже.", show_alert=True)
        return

    invoices = data.get("result", {}).get("items", [])
    if not invoices:
        await callback.answer("Счёт не найден.", show_alert=True)
        return

    invoice = invoices[0]
    if invoice.get("status") == "paid":
        await pay_repo.complete(payment.id)

        if payment.discount_applied > 0:
            db_user.has_used_referral_discount = True
            await session.commit()

        ok, link_or_err = await activate_subscription(
            session=session,
            user_id=db_user.id,
            plan_days=payment.plan_days,
        )

        if ok:
            await callback.message.edit_text(
                f"✅ <b>Оплата получена! Подписка активирована.</b>\n\n"
                f"🔗 Ссылка для подключения:\n<code>{link_or_err}</code>",
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(
                "✅ Оплата получена, ошибка активации. Обратитесь в поддержку.",
                parse_mode="HTML",
            )
    else:
        await callback.answer("Оплата ещё не поступила.", show_alert=True)


# ─── Telegram Stars ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("pay_stars_"))
async def pay_stars(callback: CallbackQuery, db_user: User, bot: Bot):
    plan = callback.data.split("_")[-1]
    price = _get_price(plan, db_user)
    days = PLAN_DAYS[plan]
    stars = get_stars_price(price)

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"VPN подписка на {days} дней",
        description=f"Безопасный VPN. Протокол VLESS+WS+TLS. 1 устройство.",
        payload=f"vpn_{plan}_{db_user.id}",
        currency="XTR",
        prices=[LabeledPrice(label="VPN подписка", amount=stars)],
    )
    await callback.answer()


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    """Telegram требует подтвердить платёж в течение 10 секунд."""
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_stars_payment(message: Message, db_user: User, session: AsyncSession):
    payload = message.successful_payment.invoice_payload
    parts = payload.split("_")
    plan = parts[1]  # month
    days = PLAN_DAYS.get(plan, 30)

    pay_repo = PaymentRepository(session)
    payment = await pay_repo.create(
        user_id=db_user.id,
        provider=PaymentProvider.TELEGRAM_STARS,
        provider_payment_id=message.successful_payment.telegram_payment_charge_id,
        amount_rub=settings.PRICE_1_MONTH if plan == "month" else 0,
        amount_paid=message.successful_payment.total_amount,
        currency="XTR",
        plan_days=days,
        discount_applied=0,
    )
    await pay_repo.complete(payment.id)

    ok, link_or_err = await activate_subscription(
        session=session,
        user_id=db_user.id,
        plan_days=days,
    )

    if ok:
        await message.answer(
            f"✅ <b>Оплата Stars прошла! Подписка активирована.</b>\n\n"
            f"🔗 Ссылка для подключения:\n<code>{link_or_err}</code>",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "✅ Оплата получена, ошибка активации. Обратитесь в поддержку.",
            parse_mode="HTML",
        )


@router.callback_query(F.data == "cancel_payment")
async def cancel_payment(callback: CallbackQuery):
    await callback.message.edit_text("❌ Оплата отменена. Вы можете вернуться к выбору тарифа в меню.")
    await callback.answer()
