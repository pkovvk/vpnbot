from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import main_menu_kb
from database import SubscriptionRepository
from database.models import User

router = Router()

WELCOME_TEXT = """
👋 Добро пожаловать в <b>VPN Bot</b>!

🔒 Безопасный и быстрый VPN без логов и ограничений.

<b>Что умеет бот:</b>
• 🎁 Бесплатный пробный период на 7 дней
• 💳 Удобная оплата: карта, крипта, Stars
• 🔑 Мгновенная выдача доступа
• 📱 Поддержка всех устройств

Выберите действие в меню ниже 👇
"""

WELCOME_BACK_TEXT = """
👋 С возвращением, <b>{name}</b>!

Используйте меню для управления подпиской.
"""


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User, session: AsyncSession):
    sub_repo = SubscriptionRepository(session)
    active_sub = await sub_repo.get_active(db_user.id)

    if active_sub:
        text = WELCOME_BACK_TEXT.format(name=message.from_user.first_name)
    else:
        text = WELCOME_TEXT

    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: Message):
    await message.answer(
        "📞 <b>Поддержка</b>\n\n"
        "По всем вопросам пишите: @your_support_username\n\n"
        "⏱ Время ответа: до 24 часов",
        parse_mode="HTML",
    )
