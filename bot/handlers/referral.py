from aiogram import Router, F, Bot
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import referral_kb
from database import UserRepository, ReferralRepository
from database.models import User

router = Router()


@router.message(F.text == "👥 Реферальная программа")
async def referral_menu(message: Message, db_user: User, session: AsyncSession, bot: Bot):
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={db_user.referral_code}"

    ref_repo = ReferralRepository(session)
    referral_count = await ref_repo.get_referral_count(db_user.id)

    text = (
        f"👥 <b>Реферальная программа</b>\n\n"
        f"Приглашайте друзей и зарабатывайте бонусы!\n\n"
        f"<b>Что вы получаете:</b>\n"
        f"💰 <b>+{50}₽</b> на баланс за каждого, кто активирует пробный период\n\n"
        f"<b>Что получает ваш друг:</b>\n"
        f"🎁 <b>Скидка 50%</b> на первую покупку подписки\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Приглашено: <b>{referral_count} чел.</b>\n"
        f"💵 Баланс: <b>{db_user.balance:.0f}₽</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🔗 Ваша ссылка:\n"
        f"<code>{ref_link}</code>"
    )

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=referral_kb(ref_link),
    )
