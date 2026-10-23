import json
import logging

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.queries import add_movie, get_movie_by_code

logger = logging.getLogger(__name__)

router = Router(name="restore")

# Caption prefix used by scripts/restore_movies.py: "#restore {json}".
RESTORE_TAG = "#restore"

# --- User-facing text (Rule of Text) -------------------------------------
# scripts/restore_movies.py matches these replies exactly; keep them in sync.
RESTORED_TEXT = "♻️ Tiklandi: {code}"
ALREADY_EXISTS_TEXT = "⏭ Allaqachon mavjud: {code}"
BAD_PAYLOAD_TEXT = "Xatolik: #restore ma'lumotlari noto'g'ri."


@router.message(F.video, F.caption.startswith(RESTORE_TAG))
async def restore_movie(message: Message, session: AsyncSession) -> None:
    """Re-register a movie re-sent by the restore script under a fresh file_id."""
    try:
        data = json.loads(message.caption[len(RESTORE_TAG):])
        code = str(data["code"]).strip()
        year = int(data["year"])
        title, country, language, genre = (
            str(data[key]).strip() for key in ("title", "country", "language", "genre")
        )
    except (ValueError, KeyError, TypeError):
        logger.warning("Bad restore payload: %r", message.caption)
        await message.answer(BAD_PAYLOAD_TEXT)
        return

    if await get_movie_by_code(session, code) is not None:
        await message.answer(ALREADY_EXISTS_TEXT.format(code=code))
        return

    await add_movie(
        session,
        code=code,
        file_id=message.video.file_id,
        title=title,
        country=country,
        year=year,
        language=language,
        genre=genre,
    )
    await message.answer(RESTORED_TEXT.format(code=code))
