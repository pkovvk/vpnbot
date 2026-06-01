from typing import Callable, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from database.engine import AsyncSessionLocal
from database.repositories import UserRepository


class DbSessionMiddleware(BaseMiddleware):
    """Инжектирует сессию БД в каждый хендлер."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with AsyncSessionLocal() as session:
            data["session"] = session
            return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    """Автоматически регистрирует/обновляет пользователя при каждом обращении."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = None

        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user and "session" in data:
            session: AsyncSession = data["session"]
            repo = UserRepository(session)

            # Проверяем реферальный код из /start
            ref_code = None
            if isinstance(event, Message) and event.text and event.text.startswith("/start "):
                parts = event.text.split()
                if len(parts) > 1:
                    ref_code = parts[1]

            db_user, _ = await repo.get_or_create(
                user_id=user.id,
                username=user.username,
                full_name=user.full_name,
                language_code=user.language_code,
                referred_by_code=ref_code,
            )
            data["db_user"] = db_user

        return await handler(event, data)


class BanMiddleware(BaseMiddleware):
    """Блокирует забаненных пользователей."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db_user = data.get("db_user")
        if db_user and db_user.is_banned:
            if isinstance(event, Message):
                await event.answer("🚫 Ваш аккаунт заблокирован. Обратитесь в поддержку.")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Аккаунт заблокирован.", show_alert=True)
            return

        return await handler(event, data)
