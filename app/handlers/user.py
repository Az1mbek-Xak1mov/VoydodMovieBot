import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Channel
from app.database.queries import (
    get_all_channels,
    get_movie_by_code,
    increment_movie_download,
    log_activity,
    update_user_verification,
    upsert_user,
)

logger = logging.getLogger(__name__)

router = Router(name="user")

SUBSCRIBED_STATUSES = ("member", "administrator", "creator")

# --- User-facing text (Rule of Text) -------------------------------------
START_TEXT = (
    "Assalomu alaykum! 🎬\n\n"
    "Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling "
    "va ✅ Tasdiqlash tugmasini bosing."
)
ALREADY_VERIFIED_TEXT = "✅ Botdan foydalanishingiz mumkin. Film kodini yozing:"
SUCCESS_TEXT = (
    "✅ Tasdiqlandi! Botdan foydalanishingiz mumkin. Film kodini yozing:"
)
MUST_SUBSCRIBE_TEXT = "Iltimos, barcha kanallarga obuna bo'ling!"

VERIFY_BUTTON_TEXT = "✅ Tasdiqlash"
VERIFY_CALLBACK = "verify_subs"

MOVIE_NOT_FOUND_TEXT = "Kechirasiz, bunday kodli film topilmadi."
MOVIE_CAPTION_TEMPLATE = (
    "🎬 {title} | Kod - {code}\n"
    "— — — — — —\n"
    "🌐 • {country}\n"
    "📆 • {year}\n"
    "🎙 • {language}\n"
    "🎭 • {genre}\n"
    "© • @{bot_username}\n"
    "📥 • Yuklandi: {download_count}"
)


def _build_subscription_keyboard(channels: list[Channel]) -> InlineKeyboardMarkup:
    """Build the forced-subscription inline keyboard from a channel list."""
    builder = InlineKeyboardBuilder()
    for channel in channels:
        username = channel.channel_username.lstrip("@")
        builder.row(
            InlineKeyboardButton(
                text=channel.title,
                url=f"https://t.me/{username}",
            )
        )
    builder.row(
        InlineKeyboardButton(text=VERIFY_BUTTON_TEXT, callback_data=VERIFY_CALLBACK)
    )
    return builder.as_markup()


async def is_subscribed_to_all(
    bot: Bot, channels: list[Channel], user_id: int
) -> bool:
    """Live-check Telegram membership for every mandatory channel.

    Returns True only if the user is a member/admin/creator of ALL channels.
    A failed lookup (e.g. bot lost admin rights) is treated as not subscribed.
    """
    for channel in channels:
        try:
            member = await bot.get_chat_member(
                chat_id=channel.channel_id, user_id=user_id
            )
        except TelegramAPIError:
            logger.warning(
                "Membership check failed for channel %s (id=%s); "
                "treating user %s as not subscribed.",
                channel.channel_username,
                channel.channel_id,
                user_id,
            )
            return False
        if member.status not in SUBSCRIBED_STATUSES:
            return False
    return True


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, bot: Bot) -> None:
    """Flow A entrypoint: upsert user, then gate on a LIVE subscription check."""
    user = message.from_user
    await upsert_user(
        session,
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
    )

    channels = await get_all_channels(session)
    if not channels:
        await update_user_verification(session, user.id, True)
        await message.answer(ALREADY_VERIFIED_TEXT)
        return

    # Re-check subscription live on every /start, never trust a stale flag.
    if await is_subscribed_to_all(bot, channels, user.id):
        await update_user_verification(session, user.id, True)
        await message.answer(ALREADY_VERIFIED_TEXT)
        return

    await update_user_verification(session, user.id, False)
    await message.answer(
        START_TEXT,
        reply_markup=_build_subscription_keyboard(channels),
    )


@router.callback_query(F.data == VERIFY_CALLBACK)
async def verify_subscriptions(
    callback: CallbackQuery,
    session: AsyncSession,
    bot: Bot,
) -> None:
    """Verify the user is subscribed to every mandatory channel."""
    user_id = callback.from_user.id
    channels = await get_all_channels(session)

    if not await is_subscribed_to_all(bot, channels, user_id):
        await callback.answer(MUST_SUBSCRIBE_TEXT, show_alert=True)
        return

    await update_user_verification(session, user_id, True)
    await log_activity(session, user_id, "VERIFIED_SUBSCRIPTION")
    await callback.message.answer(SUCCESS_TEXT)
    await callback.answer()


@router.message(F.text & ~F.text.startswith("/"))
async def retrieve_movie(message: Message, session: AsyncSession, bot: Bot) -> None:
    """Flow B: treat plain text as a movie code, gated by a LIVE sub check."""
    user_id = message.from_user.id
    code = message.text.strip()

    # Forced-subscription is re-verified live on every request, so a user who
    # unsubscribes after verifying is blocked again immediately.
    channels = await get_all_channels(session)
    if channels and not await is_subscribed_to_all(bot, channels, user_id):
        await update_user_verification(session, user_id, False)
        await message.answer(
            MUST_SUBSCRIBE_TEXT,
            reply_markup=_build_subscription_keyboard(channels),
        )
        return

    await update_user_verification(session, user_id, True)

    movie = await get_movie_by_code(session, code)
    if movie is None:
        await message.answer(MOVIE_NOT_FOUND_TEXT)
        return

    await increment_movie_download(session, movie.id)
    await log_activity(session, user_id, "REQUESTED_MOVIE", target_id=code)

    bot_info = await bot.me()
    caption = MOVIE_CAPTION_TEMPLATE.format(
        title=movie.title,
        code=movie.code,
        country=movie.country,
        year=movie.year,
        language=movie.language,
        genre=movie.genre,
        bot_username=bot_info.username,
        download_count=movie.download_count + 1,
    )
    await message.answer_video(video=movie.file_id, caption=caption)
