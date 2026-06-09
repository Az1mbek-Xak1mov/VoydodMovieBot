from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.queries import (
    add_channel,
    add_movie,
    get_admin_stats,
    get_all_channels,
    get_movie_by_code,
    remove_channel,
)
from app.states.admin_fsm import AddChannelFSM, AddMovieFSM

router = Router(name="admin")

# --- User-facing text (Rule of Text) -------------------------------------
DASHBOARD_TEXT = (
    "🛠 <b>Admin panel</b>\n\n"
    "👥 Foydalanuvchilar: {total_users}\n"
    "🎬 Filmlar: {total_movies}\n"
    "📥 Jami yuklab olishlar: {total_downloads}"
)
STATS_TEXT = (
    "📊 <b>Statistika</b>\n\n"
    "👥 Foydalanuvchilar: {total_users}\n"
    "🎬 Filmlar: {total_movies}\n"
    "📥 Jami yuklab olishlar: {total_downloads}"
)

ASK_CHANNEL_TEXT = (
    "📢 Kanal @username ini yuboring (masalan: @kinohudud).\n"
    "Avval botni o'sha kanalda admin qilganingizga ishonch hosil qiling."
)
CHANNEL_NOT_ADMIN_TEXT = (
    "Xatolik: Bot ushbu kanalda admin emas. Dastlab botni admin qiling."
)
CHANNEL_RESOLVE_ERROR_TEXT = (
    "Xatolik: Kanalni topib bo'lmadi. @username to'g'riligini tekshiring."
)
CHANNEL_ADDED_TEXT = "✅ Kanal qo'shildi: {title} ({username})"

ASK_VIDEO_TEXT = "🎬 Film videosini yuboring."
NOT_A_VIDEO_TEXT = "Iltimos, video fayl yuboring."
ASK_CODE_TEXT = "🔢 Film kodini yuboring."
CODE_EXISTS_TEXT = "Bu kod allaqachon mavjud. Boshqa kod yuboring."
ASK_METADATA_TEXT = (
    "📝 Film ma'lumotlarini yuboring (har birini yangi qatordan yoki vergul bilan):\n\n"
    "Sarlavha, Davlat, Yil, Til, Janr\n\n"
    "Masalan:\n"
    "Qora libosli odamlar 3, AQSh, 2013, O'zbek tilida, Fantastika jangari"
)
METADATA_FORMAT_ERROR_TEXT = (
    "Xatolik: 5 ta maydon kerak (Sarlavha, Davlat, Yil, Til, Janr). Qayta yuboring."
)
YEAR_ERROR_TEXT = "Xatolik: Yil butun son bo'lishi kerak. Qayta yuboring."
MOVIE_PREVIEW_TEXT = (
    "✅ Film qo'shildi!\n\n"
    "🎬 {title} | Kod - {code}\n"
    "— — — — — —\n"
    "🌐 • {country}\n"
    "📆 • {year}\n"
    "🎙 • {language}\n"
    "🎭 • {genre}"
)

NO_CHANNELS_TEXT = "Hozircha kanallar yo'q."
ASK_REMOVE_CHANNEL_TEXT = "❌ O'chirish uchun kanalni tanlang:"
CHANNEL_REMOVED_TEXT = "✅ Kanal o'chirildi."

# --- Callback data --------------------------------------------------------
CB_STATS = "admin_stats"
CB_ADD_MOVIE = "admin_add_movie"
CB_ADD_CHANNEL = "admin_add_channel"
CB_REMOVE_CHANNEL = "admin_remove_channel"
CB_DELETE_CHANNEL_PREFIX = "admin_del_ch:"


def _build_dashboard_keyboard() -> InlineKeyboardMarkup:
    """Build the admin dashboard inline keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📊 Statistika", callback_data=CB_STATS))
    builder.row(
        InlineKeyboardButton(text="🎬 Film qo'shish", callback_data=CB_ADD_MOVIE)
    )
    builder.row(
        InlineKeyboardButton(text="📢 Kanal qo'shish", callback_data=CB_ADD_CHANNEL)
    )
    builder.row(
        InlineKeyboardButton(
            text="❌ Kanal o'chirish", callback_data=CB_REMOVE_CHANNEL
        )
    )
    return builder.as_markup()


@router.message(Command("admin"))
async def cmd_admin(message: Message, session: AsyncSession) -> None:
    """Show the admin dashboard with summary stats."""
    stats = await get_admin_stats(session)
    await message.answer(
        DASHBOARD_TEXT.format(**stats),
        reply_markup=_build_dashboard_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == CB_STATS)
async def cb_stats(callback: CallbackQuery, session: AsyncSession) -> None:
    """Display aggregate statistics."""
    stats = await get_admin_stats(session)
    await callback.message.answer(STATS_TEXT.format(**stats), parse_mode="HTML")
    await callback.answer()


# --- Add Channel FSM ------------------------------------------------------
@router.callback_query(F.data == CB_ADD_CHANNEL)
async def cb_add_channel(callback: CallbackQuery, state: FSMContext) -> None:
    """Begin the add-channel flow."""
    await state.set_state(AddChannelFSM.waiting_for_channel)
    await callback.message.answer(ASK_CHANNEL_TEXT)
    await callback.answer()


@router.message(StateFilter(AddChannelFSM.waiting_for_channel))
async def process_channel(
    message: Message, session: AsyncSession, state: FSMContext, bot: Bot
) -> None:
    """Resolve the channel, verify the bot is admin, then persist it."""
    username = message.text.strip()

    try:
        chat = await bot.get_chat(username)
    except TelegramAPIError:
        await message.answer(CHANNEL_RESOLVE_ERROR_TEXT)
        return

    # If the bot is not an admin, Telegram raises "member list is inaccessible";
    # treat any failure here as the bot lacking admin rights.
    try:
        bot_member = await bot.get_chat_member(chat.id, bot.id)
    except TelegramAPIError:
        await message.answer(CHANNEL_NOT_ADMIN_TEXT)
        return

    if bot_member.status not in ("administrator", "creator"):
        await message.answer(CHANNEL_NOT_ADMIN_TEXT)
        return

    stored_username = f"@{chat.username}" if chat.username else username
    await add_channel(
        session,
        channel_id=chat.id,
        username=stored_username,
        title=chat.title or stored_username,
    )
    await state.clear()
    await message.answer(
        CHANNEL_ADDED_TEXT.format(
            title=chat.title or stored_username, username=stored_username
        )
    )


# --- Add Movie FSM --------------------------------------------------------
@router.callback_query(F.data == CB_ADD_MOVIE)
async def cb_add_movie(callback: CallbackQuery, state: FSMContext) -> None:
    """Begin the add-movie flow."""
    await state.set_state(AddMovieFSM.waiting_for_video)
    await callback.message.answer(ASK_VIDEO_TEXT)
    await callback.answer()


@router.message(StateFilter(AddMovieFSM.waiting_for_video))
async def process_video(message: Message, state: FSMContext) -> None:
    """Capture the video file_id."""
    if message.video is None:
        await message.answer(NOT_A_VIDEO_TEXT)
        return
    await state.update_data(file_id=message.video.file_id)
    await state.set_state(AddMovieFSM.waiting_for_code)
    await message.answer(ASK_CODE_TEXT)


@router.message(StateFilter(AddMovieFSM.waiting_for_code))
async def process_code(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Validate uniqueness of the code, then advance to metadata."""
    code = message.text.strip()
    existing = await get_movie_by_code(session, code)
    if existing is not None:
        await message.answer(CODE_EXISTS_TEXT)
        return
    await state.update_data(code=code)
    await state.set_state(AddMovieFSM.waiting_for_metadata)
    await message.answer(ASK_METADATA_TEXT)


@router.message(StateFilter(AddMovieFSM.waiting_for_metadata))
async def process_metadata(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Parse metadata, persist the movie, and send a preview."""
    raw = message.text.strip()
    parts = raw.split("\n") if "\n" in raw else raw.split(",")
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) != 5:
        await message.answer(METADATA_FORMAT_ERROR_TEXT)
        return

    title, country, year_raw, language, genre = parts
    try:
        year = int(year_raw)
    except ValueError:
        await message.answer(YEAR_ERROR_TEXT)
        return

    data = await state.get_data()
    await add_movie(
        session,
        code=data["code"],
        file_id=data["file_id"],
        title=title,
        country=country,
        year=year,
        language=language,
        genre=genre,
    )
    await state.clear()
    await message.answer(
        MOVIE_PREVIEW_TEXT.format(
            title=title,
            code=data["code"],
            country=country,
            year=year,
            language=language,
            genre=genre,
        )
    )


# --- Remove Channel -------------------------------------------------------
@router.callback_query(F.data == CB_REMOVE_CHANNEL)
async def cb_remove_channel(callback: CallbackQuery, session: AsyncSession) -> None:
    """List channels with delete buttons."""
    channels = await get_all_channels(session)
    if not channels:
        await callback.message.answer(NO_CHANNELS_TEXT)
        await callback.answer()
        return

    builder = InlineKeyboardBuilder()
    for channel in channels:
        builder.row(
            InlineKeyboardButton(
                text=f"❌ {channel.title}",
                callback_data=f"{CB_DELETE_CHANNEL_PREFIX}{channel.channel_id}",
            )
        )
    await callback.message.answer(
        ASK_REMOVE_CHANNEL_TEXT, reply_markup=builder.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith(CB_DELETE_CHANNEL_PREFIX))
async def cb_delete_channel(callback: CallbackQuery, session: AsyncSession) -> None:
    """Delete the selected channel."""
    channel_id = int(callback.data.removeprefix(CB_DELETE_CHANNEL_PREFIX))
    await remove_channel(session, channel_id)
    await callback.message.answer(CHANNEL_REMOVED_TEXT)
    await callback.answer()
