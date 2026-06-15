import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from openai import OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.queries import (
    add_channel,
    add_movie,
    get_admin_stats,
    get_all_channels,
    get_movie_by_code,
    remove_channel,
)
from app.services.image import MAX_EDIT_IMAGES, edit_image, generate_image
from app.states.admin_fsm import AddChannelFSM, AddMovieFSM, ImageFSM

logger = logging.getLogger(__name__)

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

# --- AI Image generation / editing ---------------------------------------
ASK_GEN_PROMPT_TEXT = (
    "🎨 Rasm uchun tavsif (prompt) yuboring.\n\n"
    "Masalan: <i>Tokio shahridagi tungi ko'cha, neon chiroqlar, kinematik yorug'lik, "
    "fotorealistik</i>"
)
ASK_EDIT_INPUT_TEXT = (
    "🖌 Tahrirlash uchun 1 yoki bir nechta rasm yuboring "
    "(eng ko'pi {max} ta), so'ng nima qilish kerakligini matn (prompt) bilan yuboring.\n\n"
    "Masalan: <i>Fonni zamonaviy ofisga almashtir. Insonni o'zgartirma. "
    "Professional yorug'lik.</i>"
).format(max=MAX_EDIT_IMAGES)
EDIT_IMAGE_RECEIVED_TEXT = (
    "✅ Rasm qabul qilindi ({count} ta). Yana rasm yuboring "
    "yoki tahrirlash uchun matn (prompt) yuboring."
)
EDIT_MAX_IMAGES_TEXT = (
    "⚠️ Eng ko'pi {max} ta rasm. Tahrirlash uchun matn (prompt) yuboring."
).format(max=MAX_EDIT_IMAGES)
EDIT_NO_IMAGE_YET_TEXT = "Avval kamida bitta rasm yuboring."
EDIT_SEND_PROMPT_TEXT = "Matn (prompt) yoki rasm yuboring."
GENERATING_TEXT = "⏳ Rasm yaratilmoqda... (30–60 soniya)"
EDITING_TEXT = "⏳ Rasm tahrirlanmoqda... (30–60 soniya)"
IMAGE_ERROR_TEXT = (
    "❌ Rasmni yaratib bo'lmadi. Promptni o'zgartirib qayta urinib ko'ring "
    "(noo'rin yoki taqiqlangan kontent rad etilishi mumkin)."
)
RESULT_GEN_CAPTION = "🎨 Tayyor!\n\n{prompt}"
RESULT_EDIT_CAPTION = "🖌 Tahrirlandi!\n\n{prompt}"
# Telegram caption hard limit is 1024 chars; keep prompt well under it.
_CAPTION_PROMPT_LIMIT = 800

# --- Callback data --------------------------------------------------------
CB_STATS = "admin_stats"
CB_ADD_MOVIE = "admin_add_movie"
CB_ADD_CHANNEL = "admin_add_channel"
CB_REMOVE_CHANNEL = "admin_remove_channel"
CB_DELETE_CHANNEL_PREFIX = "admin_del_ch:"
CB_GEN_IMAGE = "admin_gen_image"
CB_EDIT_IMAGE = "admin_edit_image"


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
    builder.row(
        InlineKeyboardButton(text="🎨 Rasm yaratish", callback_data=CB_GEN_IMAGE)
    )
    builder.row(
        InlineKeyboardButton(
            text="🖌 Rasmni tahrirlash", callback_data=CB_EDIT_IMAGE
        )
    )
    return builder.as_markup()


@router.message(Command("admin"))
async def cmd_admin(
    message: Message, session: AsyncSession, state: FSMContext
) -> None:
    """Show the admin dashboard with summary stats."""
    # Always reset any half-finished flow so /admin is a clean entry point.
    await state.clear()
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


# --- AI Image: generate from a prompt -------------------------------------
def _caption(template: str, prompt: str) -> str:
    """Format a result caption, truncating the prompt to Telegram's limit."""
    trimmed = prompt[:_CAPTION_PROMPT_LIMIT]
    if len(prompt) > _CAPTION_PROMPT_LIMIT:
        trimmed += "…"
    return template.format(prompt=trimmed)


@router.callback_query(F.data == CB_GEN_IMAGE)
async def cb_gen_image(callback: CallbackQuery, state: FSMContext) -> None:
    """Begin the text-to-image flow."""
    await state.set_state(ImageFSM.waiting_for_gen_prompt)
    await callback.message.answer(ASK_GEN_PROMPT_TEXT, parse_mode="HTML")
    await callback.answer()


@router.message(
    StateFilter(ImageFSM.waiting_for_gen_prompt),
    F.text & ~F.text.startswith("/"),
)
async def process_gen_prompt(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    """Generate an image from the admin's prompt and send it back."""
    prompt = message.text.strip()
    await state.clear()

    status = await message.answer(GENERATING_TEXT)
    await bot.send_chat_action(message.chat.id, "upload_photo")
    try:
        png = await generate_image(prompt)
    except OpenAIError as exc:
        logger.exception("Image generation failed: %s", exc)
        await status.edit_text(IMAGE_ERROR_TEXT)
        return

    await status.delete()
    await message.answer_photo(
        BufferedInputFile(png, filename="generated.png"),
        caption=_caption(RESULT_GEN_CAPTION, prompt),
    )


@router.message(StateFilter(ImageFSM.waiting_for_gen_prompt))
async def gen_prompt_fallback(message: Message) -> None:
    """Nudge the admin to send a text prompt for generation."""
    await message.answer(ASK_GEN_PROMPT_TEXT, parse_mode="HTML")


# --- AI Image: edit one or more reference images --------------------------
def _extract_image_file_id(message: Message) -> str | None:
    """Return the file_id of an image sent as a photo or image document."""
    if message.photo:
        return message.photo[-1].file_id
    document = message.document
    if document is not None and (document.mime_type or "").startswith("image/"):
        return document.file_id
    return None


@router.callback_query(F.data == CB_EDIT_IMAGE)
async def cb_edit_image(callback: CallbackQuery, state: FSMContext) -> None:
    """Begin the image-edit flow."""
    await state.set_state(ImageFSM.waiting_for_edit_input)
    await state.update_data(edit_file_ids=[])
    await callback.message.answer(ASK_EDIT_INPUT_TEXT, parse_mode="HTML")
    await callback.answer()


@router.message(
    StateFilter(ImageFSM.waiting_for_edit_input),
    F.photo | F.document,
)
async def process_edit_image(message: Message, state: FSMContext) -> None:
    """Collect a reference image to be edited."""
    file_id = _extract_image_file_id(message)
    if file_id is None:
        await message.answer(EDIT_SEND_PROMPT_TEXT)
        return

    data = await state.get_data()
    file_ids: list[str] = data.get("edit_file_ids", [])
    if len(file_ids) >= MAX_EDIT_IMAGES:
        await message.answer(EDIT_MAX_IMAGES_TEXT)
        return

    file_ids.append(file_id)
    await state.update_data(edit_file_ids=file_ids)
    await message.answer(EDIT_IMAGE_RECEIVED_TEXT.format(count=len(file_ids)))


@router.message(
    StateFilter(ImageFSM.waiting_for_edit_input),
    F.text & ~F.text.startswith("/"),
)
async def process_edit_prompt(
    message: Message, state: FSMContext, bot: Bot
) -> None:
    """Run the edit using the collected images and the admin's prompt."""
    data = await state.get_data()
    file_ids: list[str] = data.get("edit_file_ids", [])
    if not file_ids:
        await message.answer(EDIT_NO_IMAGE_YET_TEXT)
        return

    prompt = message.text.strip()
    await state.clear()

    status = await message.answer(EDITING_TEXT)
    await bot.send_chat_action(message.chat.id, "upload_photo")
    try:
        images = [(await bot.download(file_id)).read() for file_id in file_ids]
        png = await edit_image(images, prompt)
    except (OpenAIError, TelegramAPIError) as exc:
        logger.exception("Image edit failed: %s", exc)
        await status.edit_text(IMAGE_ERROR_TEXT)
        return

    await status.delete()
    await message.answer_photo(
        BufferedInputFile(png, filename="edited.png"),
        caption=_caption(RESULT_EDIT_CAPTION, prompt),
    )


@router.message(StateFilter(ImageFSM.waiting_for_edit_input))
async def edit_input_fallback(message: Message) -> None:
    """Guide the admin when they send neither an image nor a prompt."""
    await message.answer(EDIT_SEND_PROMPT_TEXT)
