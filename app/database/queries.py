from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import ActivityLog, Channel, Movie, User


async def upsert_user(
    session: AsyncSession,
    user_id: int,
    username: str | None,
    full_name: str,
) -> User:
    """Insert a new user or update mutable fields of an existing one."""
    user = await session.get(User, user_id)
    if user is None:
        user = User(id=user_id, username=username, full_name=full_name)
        session.add(user)
    else:
        user.username = username
        user.full_name = full_name
    await session.commit()
    await session.refresh(user)
    return user


async def get_user(session: AsyncSession, user_id: int) -> User | None:
    """Fetch a single user by Telegram ID."""
    return await session.get(User, user_id)


async def update_user_verification(
    session: AsyncSession,
    user_id: int,
    is_verified: bool,
) -> None:
    """Set the forced-subscription verification flag for a user."""
    user = await session.get(User, user_id)
    if user is not None:
        user.is_verified = is_verified
        await session.commit()


async def get_all_channels(session: AsyncSession) -> list[Channel]:
    """Return every mandatory-subscription channel."""
    result = await session.execute(select(Channel))
    return list(result.scalars().all())


async def add_channel(
    session: AsyncSession,
    channel_id: int,
    username: str,
    title: str,
) -> Channel:
    """Add a mandatory-subscription channel."""
    channel = Channel(channel_id=channel_id, channel_username=username, title=title)
    session.add(channel)
    await session.commit()
    await session.refresh(channel)
    return channel


async def remove_channel(session: AsyncSession, channel_id: int) -> None:
    """Remove a channel by its internal Telegram chat ID."""
    result = await session.execute(
        select(Channel).where(Channel.channel_id == channel_id)
    )
    channel = result.scalar_one_or_none()
    if channel is not None:
        await session.delete(channel)
        await session.commit()


async def get_movie_by_code(session: AsyncSession, code: str) -> Movie | None:
    """Fetch a movie by its unique code."""
    result = await session.execute(select(Movie).where(Movie.code == code))
    return result.scalar_one_or_none()


async def add_movie(
    session: AsyncSession,
    code: str,
    file_id: str,
    title: str,
    country: str,
    year: int,
    language: str,
    genre: str,
) -> Movie:
    """Persist a new movie record."""
    movie = Movie(
        code=code,
        file_id=file_id,
        title=title,
        country=country,
        year=year,
        language=language,
        genre=genre,
    )
    session.add(movie)
    await session.commit()
    await session.refresh(movie)
    return movie


async def increment_movie_download(session: AsyncSession, movie_id: int) -> None:
    """Atomically increment a movie's download counter."""
    await session.execute(
        update(Movie)
        .where(Movie.id == movie_id)
        .values(download_count=Movie.download_count + 1)
    )
    await session.commit()


async def log_activity(
    session: AsyncSession,
    user_id: int,
    action: str,
    target_id: str | None = None,
) -> None:
    """Record a user action for the admin stats panel."""
    entry = ActivityLog(user_id=user_id, action=action, target_id=target_id)
    session.add(entry)
    await session.commit()


async def get_admin_stats(session: AsyncSession) -> dict[str, int]:
    """Return aggregate counts for the admin dashboard."""
    total_users = await session.scalar(select(func.count()).select_from(User))
    total_movies = await session.scalar(select(func.count()).select_from(Movie))
    total_downloads = await session.scalar(select(func.coalesce(func.sum(Movie.download_count), 0)))
    return {
        "total_users": total_users or 0,
        "total_movies": total_movies or 0,
        "total_downloads": total_downloads or 0,
    }
