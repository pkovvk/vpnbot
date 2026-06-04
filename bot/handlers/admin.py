import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, PhotoSize
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import admin_main_kb, admin_broadcast_type_kb, admin_confirm_kb
from config import settings
from database import (
    UserRepository, SubscriptionRepository, PaymentRepository,
    SubscriptionStatus,
)
from database.models import User
from services.subscription import activate_subscription, revoke_subscription

logger = logging.getLogger(__name__)
router = Router()


# ─── FSM States ──────────────────────────────────────────────────────────────

class AdminStates(StatesGroup):
    # Выдача подписки
    waiting_user_id_grant = State()
    waiting_days_grant = State()

    # Отзыв подписки
    waiting_user_id_revoke = State()

    # Рассылка
    broadcast_choosing_type = State()
    broadcast_waiting_text = State()
    broadcast_waiting_photo = State()
    broadcast_confirm = State()

    # Поиск пользователя
    waiting_find_user = State()

    # Изменение баланса
    waiting_user_id_balance = State()
    waiting_balance_amount = State()

    # Отправка сообщения по ID
    waiting_user_id_send = State()
    waiting_message_send = State()
    send_confirm = State()


# ─── Фильтр для администраторов ──────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


# ─── Главная панель ───────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return

    await message.answer(
        "🛠 <b>Панель администратора</b>",
        parse_mode="HTML",
        reply_markup=admin_main_kb(),
    )


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    user_repo = UserRepository(session)
    stats = await user_repo.get_stats()

    await callback.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"👤 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"✅ Активных подписок: <b>{stats['active_subscriptions']}</b>\n"
        f"💰 Общий доход: <b>{stats['total_revenue']:.0f}₽</b>",
        parse_mode="HTML",
        reply_markup=admin_main_kb(),
    )
    await callback.answer()


# ─── Выдача подписки ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_grant")
async def admin_grant_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text(
        "✅ <b>Выдача подписки</b>\n\n"
        "Введите Telegram ID пользователя:",
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.waiting_user_id_grant)
    await callback.answer()


@router.message(AdminStates.waiting_user_id_grant)
async def admin_grant_user_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите числовой ID.")
        return

    await state.update_data(target_user_id=user_id)
    await message.answer(
        "На сколько дней выдать подписку?\n(Например: 30, 7, 90)"
    )
    await state.set_state(AdminStates.waiting_days_grant)


@router.message(AdminStates.waiting_days_grant)
async def admin_grant_days(message: Message, state: FSMContext, session: AsyncSession):
    if not is_admin(message.from_user.id):
        return

    try:
        days = int(message.text.strip())
        assert 1 <= days <= 3650
    except (ValueError, AssertionError):
        await message.answer("❌ Введите число от 1 до 3650.")
        return

    data = await state.get_data()
    target_id = data["target_user_id"]

    ok, result = await activate_subscription(
        session=session,
        user_id=target_id,
        plan_days=days,
        is_trial=False,
    )

    if ok:
        await message.answer(
            f"✅ Подписка на <b>{days} дней</b> выдана пользователю <code>{target_id}</code>.\n\n"
            f"Ссылка: <code>{result}</code>",
            parse_mode="HTML",
        )
        try:
            await message.bot.send_message(
                target_id,
                f"🎁 Администратор выдал вам подписку на <b>{days} дней</b>!\n\n"
                f"🔗 Ссылка для подключения:\n<code>{result}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        await message.answer(f"❌ Ошибка: {result}")

    await state.clear()


# ─── Отзыв подписки ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_revoke")
async def admin_revoke_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text(
        "❌ <b>Отзыв подписки</b>\n\n"
        "Введите Telegram ID пользователя:",
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.waiting_user_id_revoke)
    await callback.answer()


@router.message(AdminStates.waiting_user_id_revoke)
async def admin_revoke_confirm(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите числовой ID.")
        return

    await state.update_data(target_user_id=user_id)
    await message.answer(
        f"Отозвать подписку у пользователя <code>{user_id}</code>?",
        parse_mode="HTML",
        reply_markup=admin_confirm_kb("revoke"),
    )


@router.callback_query(F.data == "confirm_revoke")
async def admin_revoke_do(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    data = await state.get_data()
    target_id = data.get("target_user_id")

    ok = await revoke_subscription(session, target_id, reason="manual")

    if ok:
        await callback.message.edit_text(
            f"✅ Подписка пользователя <code>{target_id}</code> отозвана.",
            parse_mode="HTML",
        )
        try:
            await callback.bot.send_message(
                target_id,
                "⚠️ Ваша подписка была приостановлена администратором. "
                "Если это ошибка — обратитесь в поддержку.",
            )
        except Exception:
            pass
    else:
        await callback.message.edit_text("❌ Активная подписка не найдена.")

    await state.clear()
    await callback.answer()


# ─── Рассылка ────────────────────────────────────────────────────────────────

class BroadcastData:
    text: str | None = None
    photo_id: str | None = None


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\nВыберите тип рассылки:",
        parse_mode="HTML",
        reply_markup=admin_broadcast_type_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "broadcast_text")
async def broadcast_text_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text(
        "📝 Введите текст рассылки (поддерживается HTML разметка):"
    )
    await state.set_state(AdminStates.broadcast_waiting_text)
    await state.update_data(broadcast_photo=None)
    await callback.answer()


@router.callback_query(F.data == "broadcast_photo")
async def broadcast_photo_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return

    await callback.message.edit_text("🖼 Отправьте фото (можно с подписью — она станет текстом рассылки):")
    await state.set_state(AdminStates.broadcast_waiting_photo)
    await callback.answer()


@router.message(AdminStates.broadcast_waiting_photo, F.photo)
async def broadcast_got_photo(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    photo: PhotoSize = message.photo[-1]
    caption = message.caption or ""

    await state.update_data(broadcast_photo=photo.file_id, broadcast_text=caption)
    await message.answer(
        f"📋 <b>Предпросмотр рассылки:</b>\n\n{caption or '(без текста)'}",
        parse_mode="HTML",
        reply_markup=admin_confirm_kb("broadcast"),
    )
    await state.set_state(AdminStates.broadcast_confirm)


@router.message(AdminStates.broadcast_waiting_text)
async def broadcast_got_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.update_data(broadcast_text=message.text, broadcast_photo=None)
    await message.answer(
        f"📋 <b>Предпросмотр рассылки:</b>\n\n{message.text}",
        parse_mode="HTML",
        reply_markup=admin_confirm_kb("broadcast"),
    )
    await state.set_state(AdminStates.broadcast_confirm)


@router.callback_query(F.data == "confirm_broadcast")
async def broadcast_send(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    data = await state.get_data()
    text = data.get("broadcast_text", "")
    photo_id = data.get("broadcast_photo")

    user_repo = UserRepository(session)
    user_ids = await user_repo.get_all_active_ids()

    await callback.message.edit_text(
        f"📢 Начинаем рассылку для {len(user_ids)} пользователей..."
    )

    sent = 0
    failed = 0

    for user_id in user_ids:
        try:
            if photo_id:
                await bot.send_photo(user_id, photo=photo_id, caption=text, parse_mode="HTML")
            else:
                await bot.send_message(user_id, text, parse_mode="HTML")
            sent += 1
        except Exception as e:
            failed += 1
            logger.debug(f"Broadcast failed for {user_id}: {e}")

        await asyncio.sleep(0.05)  # Не спамим Telegram API

    await callback.message.answer(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"📨 Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}",
        parse_mode="HTML",
    )

    await state.clear()
    await callback.answer()


# ─── Поиск пользователя ───────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_find_user")
async def admin_find_user_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text("🔍 Введите Telegram ID пользователя:")
    await state.set_state(AdminStates.waiting_find_user)
    await callback.answer()


@router.message(AdminStates.waiting_find_user)
async def admin_find_user_result(message: Message, state: FSMContext, session: AsyncSession):
    if not is_admin(message.from_user.id):
        return

    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите числовой ID.")
        return

    user_repo = UserRepository(session)
    sub_repo = SubscriptionRepository(session)

    user = await user_repo.get_by_id(user_id)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        await state.clear()
        return

    sub = await sub_repo.get_active(user_id)
    sub_info = "нет активной подписки"
    if sub:
        sub_info = f"{sub.status.value} до {sub.expires_at.strftime('%d.%m.%Y')}"

    await message.answer(
        f"👤 <b>Пользователь:</b>\n\n"
        f"ID: <code>{user.id}</code>\n"
        f"Имя: {user.full_name}\n"
        f"Username: @{user.username or '—'}\n"
        f"Баланс: {user.balance:.0f}₽\n"
        f"Реф. код: <code>{user.referral_code}</code>\n"
        f"Триал использован: {'да' if user.has_used_trial else 'нет'}\n"
        f"Забанен: {'да' if user.is_banned else 'нет'}\n"
        f"Подписка: {sub_info}",
        parse_mode="HTML",
    )
    await state.clear()


# ─── Изменение баланса ────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_balance")
async def admin_balance_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text(
        "💰 <b>Изменение баланса</b>\n\n"
        "Введите Telegram ID пользователя:",
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.waiting_user_id_balance)
    await callback.answer()


@router.message(AdminStates.waiting_user_id_balance)
async def admin_balance_user_id(message: Message, state: FSMContext, session: AsyncSession):
    if not is_admin(message.from_user.id):
        return

    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите числовой ID.")
        return

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        await state.clear()
        return

    await state.update_data(target_user_id=user_id)
    await message.answer(
        f"👤 Пользователь <code>{user_id}</code> | Текущий баланс: <b>{user.balance:.0f}₽</b>\n\n"
        f"Введите сумму изменения:\n"
        f"• <code>+500</code> — пополнить на 500₽\n"
        f"• <code>-200</code> — списать 200₽\n"
        f"• <code>=1000</code> — установить баланс 1000₽",
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.waiting_balance_amount)


@router.message(AdminStates.waiting_balance_amount)
async def admin_balance_apply(message: Message, state: FSMContext, session: AsyncSession):
    if not is_admin(message.from_user.id):
        return

    raw = message.text.strip()
    data = await state.get_data()
    target_id = data["target_user_id"]

    user_repo = UserRepository(session)
    user: User = await user_repo.get_by_id(target_id)
    if not user:
        await message.answer("❌ Пользователь не найден.")
        await state.clear()
        return

    old_balance = user.balance

    try:
        if raw.startswith("="):
            new_balance = float(raw[1:])
            if new_balance < 0:
                raise ValueError
            action_text = f"установлен в {new_balance:.0f}₽"
        elif raw.startswith("+"):
            delta = float(raw[1:])
            if delta <= 0:
                raise ValueError
            new_balance = old_balance + delta
            action_text = f"пополнен на {delta:.0f}₽"
        elif raw.startswith("-"):
            delta = float(raw[1:])
            if delta <= 0:
                raise ValueError
            new_balance = max(0.0, old_balance - delta)
            action_text = f"списано {delta:.0f}₽ (было {old_balance:.0f}₽)"
        else:
            raise ValueError
    except (ValueError, IndexError):
        await message.answer(
            "❌ Неверный формат. Используйте:\n"
            "<code>+500</code> — пополнить\n"
            "<code>-200</code> — списать\n"
            "<code>=1000</code> — установить",
            parse_mode="HTML",
        )
        return

    user.balance = new_balance
    await session.commit()

    await message.answer(
        f"✅ Баланс пользователя <code>{target_id}</code> {action_text}.\n"
        f"Новый баланс: <b>{new_balance:.0f}₽</b>",
        parse_mode="HTML",
        reply_markup=admin_main_kb(),
    )

    try:
        await message.bot.send_message(
            target_id,
            f"💰 Ваш баланс изменён администратором.\n"
            f"Было: <b>{old_balance:.0f}₽</b> → Стало: <b>{new_balance:.0f}₽</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await state.clear()


# ─── Отправка сообщения пользователю по ID ───────────────────────────────────

@router.callback_query(F.data == "admin_send_message")
async def admin_send_message_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text(
        "✉️ <b>Отправка сообщения пользователю</b>\n\n"
        "Введите Telegram ID пользователя:",
        parse_mode="HTML",
    )
    await state.set_state(AdminStates.waiting_user_id_send)
    await callback.answer()


@router.message(AdminStates.waiting_user_id_send)
async def admin_send_message_user_id(message: Message, state: FSMContext, session: AsyncSession):
    if not is_admin(message.from_user.id):
        return

    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите числовой ID.")
        return

    # Проверяем существование пользователя в БД
    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if not user:
        await message.answer(
            f"⚠️ Пользователь <code>{user_id}</code> не найден в базе данных.\n"
            "Всё равно попробовать отправить сообщение? Введите текст или /cancel для отмены.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"👤 Пользователь найден: <b>{user.full_name}</b> (<code>{user_id}</code>)\n\n"
            "📝 Введите текст сообщения (поддерживается HTML разметка):",
            parse_mode="HTML",
        )

    await state.update_data(target_user_id=user_id)
    await state.set_state(AdminStates.waiting_message_send)


@router.message(AdminStates.waiting_message_send)
async def admin_send_message_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    # Поддержка фото с подписью
    if message.photo:
        photo: PhotoSize = message.photo[-1]
        caption = message.caption or ""
        await state.update_data(send_photo=photo.file_id, send_text=caption)
        preview_text = caption or "(без текста)"
        await message.answer(
            f"📋 <b>Предпросмотр сообщения:</b>\n\n🖼 [Фото]\n{preview_text}",
            parse_mode="HTML",
            reply_markup=admin_confirm_kb("send_message"),
        )
    else:
        await state.update_data(send_text=message.text, send_photo=None)
        await message.answer(
            f"📋 <b>Предпросмотр сообщения:</b>\n\n{message.text}",
            parse_mode="HTML",
            reply_markup=admin_confirm_kb("send_message"),
        )

    await state.set_state(AdminStates.send_confirm)


@router.callback_query(F.data == "confirm_send_message")
async def admin_send_message_do(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    data = await state.get_data()
    target_id = data.get("target_user_id")
    text = data.get("send_text", "")
    photo_id = data.get("send_photo")

    try:
        if photo_id:
            await bot.send_photo(
                chat_id=target_id,
                photo=photo_id,
                caption=text,
                parse_mode="HTML",
            )
        else:
            await bot.send_message(
                chat_id=target_id,
                text=text,
                parse_mode="HTML",
            )

        await callback.message.edit_text(
            f"✅ Сообщение успешно отправлено пользователю <code>{target_id}</code>.",
            parse_mode="HTML",
            reply_markup=admin_main_kb(),
        )
        logger.info(f"Admin {callback.from_user.id} sent message to user {target_id}")

    except Exception as e:
        await callback.message.edit_text(
            f"❌ Не удалось отправить сообщение пользователю <code>{target_id}</code>.\n\n"
            f"Причина: <code>{e}</code>",
            parse_mode="HTML",
            reply_markup=admin_main_kb(),
        )
        logger.warning(f"Failed to send message to {target_id}: {e}")

    await state.clear()
    await callback.answer()


# ─── Общая отмена ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_cancel")
async def admin_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Панель администратора</b>",
        parse_mode="HTML",
        reply_markup=admin_main_kb(),
    )
    await callback.answer()