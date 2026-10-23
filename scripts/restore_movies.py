"""Recover lost movies from the admin's chat history with the bot.

The videos survive the lost database: every movie the admin uploaded is still
in the admin's private chat with the bot, followed by the bot's
"✅ Film qo'shildi!" confirmation carrying its code and metadata. This script
logs in as that admin (a normal Telegram user session via Telethon) and:

  scan  reads the whole chat, pairs each confirmation with its video and
        writes restore_plan.json. Sends nothing.
  send  re-sends each planned video to the bot *by reference* (no download,
        no re-upload; instant even for 2 GB files) with a "#restore {json}"
        caption. app/handlers/restore.py saves it under the bot's file_id and
        replies; a movie is marked done only after that reply arrives.

Progress is appended to restore_done.txt, so `send` can be stopped and resumed.

Setup: get TG_API_ID / TG_API_HASH at https://my.telegram.org, then
    pip install -r scripts/requirements.txt
    TG_API_ID=... TG_API_HASH=... python scripts/restore_movies.py scan --bot @YourBot
"""

import argparse
import asyncio
import json
import os
import random
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError

# Bot texts from app/handlers/admin.py that the scan keys on.
ASK_CODE_TEXT = "🔢 Film kodini yuboring."
MOVIE_ADDED_HEADER = "✅ Film qo'shildi!"

# Must match app/handlers/restore.py.
RESTORE_TAG = "#restore"
RESTORED_TEXT = "♻️ Tiklandi: {code}"
ALREADY_EXISTS_TEXT = "⏭ Allaqachon mavjud: {code}"

PLAN_PATH = Path("restore_plan.json")
DONE_PATH = Path("restore_done.txt")
MOVIE_FIELDS = ("code", "title", "country", "year", "language", "genre")
REPLY_TIMEOUT = 60
MAX_CONSECUTIVE_FAILURES = 3


def parse_movie_card(text: str) -> dict | None:
    """Parse the movie card the bot prints in confirmations and user captions.

        🎬 {title} | Kod - {code}
        — — — — — —
        🌐 • {country}
        📆 • {year}
        🎙 • {language}
        🎭 • {genre}
    """
    lines = text.split("\n")
    head = next((i for i, line in enumerate(lines) if " | Kod - " in line), None)
    if head is None:
        return None
    fields = lines[head + 2 : head + 6]
    if len(fields) != 4 or not all(" • " in field for field in fields):
        return None

    title, code = lines[head].split(" ", 1)[1].rsplit(" | Kod - ", 1)
    country, year, language, genre = (field.split(" • ", 1)[1].strip() for field in fields)
    if not year.isdigit():
        return None
    return {
        "code": code.strip(),
        "title": title.strip(),
        "country": country,
        "year": int(year),
        "language": language,
        "genre": genre,
    }


async def scan(client: TelegramClient, bot) -> None:
    """Walk the chat oldest-first and build the restore plan."""
    movies: dict[str, dict] = {}
    from_captions: dict[str, dict] = {}
    orphans: list[str] = []
    duplicates = 0
    scanned = 0
    last_video = accepted_video = None

    async for msg in client.iter_messages(bot, reverse=True):
        scanned += 1
        text = msg.message or ""
        if msg.out:
            if msg.video and not text.startswith(RESTORE_TAG):
                last_video = msg
            continue

        if text == ASK_CODE_TEXT:
            # The bot asks for the code right after it accepts a video.
            accepted_video = last_video
        elif text.startswith(MOVIE_ADDED_HEADER):
            card = parse_movie_card(text)
            video = accepted_video or last_video
            accepted_video = last_video = None
            if card is None:
                continue
            if video is None:
                orphans.append(card["code"])
                continue
            if card["code"] in movies:
                duplicates += 1
            movies[card["code"]] = {**card, "msg_id": video.id, "source": "upload"}
        elif msg.video:
            # Fallback: a movie the bot sent back to the admin with its caption.
            card = parse_movie_card(text)
            if card is not None:
                from_captions[card["code"]] = {**card, "msg_id": msg.id, "source": "bot_caption"}

    recovered = 0
    for code, movie in from_captions.items():
        if code not in movies:
            movies[code] = movie
            recovered += 1
    orphans = [code for code in orphans if code not in movies]

    PLAN_PATH.write_text(
        json.dumps(list(movies.values()), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Scanned {scanned} messages.")
    print(f"Movies to restore: {len(movies)} ({recovered} recovered from bot captions)")
    print(f"Duplicate codes (latest kept): {duplicates}")
    if orphans:
        print(f"Confirmations whose video is gone ({len(orphans)}): {', '.join(orphans)}")
    print(f"Plan written to {PLAN_PATH}. Review it, then run `send --limit 3` as a test.")


async def send_one(client: TelegramClient, bot, movie: dict) -> str:
    """Re-send one video with its #restore caption and return the bot's reply."""
    # Re-fetch so the file reference is fresh; stale ones are rejected.
    msg = await client.get_messages(bot, ids=movie["msg_id"])
    if msg is None or not msg.video:
        return "<video message no longer exists>"

    payload = json.dumps({key: movie[key] for key in MOVIE_FIELDS}, ensure_ascii=False)
    async with client.conversation(bot, timeout=REPLY_TIMEOUT) as conv:
        await conv.send_file(msg.media, caption=f"{RESTORE_TAG} {payload}")
        reply = await conv.get_response()
    return reply.raw_text


async def send(client: TelegramClient, bot, delay: float, limit: int | None) -> None:
    """Send every not-yet-done movie in the plan, pausing between sends."""
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    done = set(DONE_PATH.read_text(encoding="utf-8").splitlines()) if DONE_PATH.exists() else set()
    todo = [movie for movie in plan if movie["code"] not in done][:limit]
    print(f"{len(done)} already done, sending {len(todo)} of {len(plan)}.")

    failed: list[str] = []
    consecutive_failures = 0
    with DONE_PATH.open("a", encoding="utf-8") as done_file:
        for index, movie in enumerate(todo, 1):
            code = movie["code"]
            try:
                reply = await send_one(client, bot, movie)
            except FloodWaitError as e:
                print(f"Flood wait: sleeping {e.seconds}s, then retrying {code}.")
                await asyncio.sleep(e.seconds + 5)
                reply = await send_one(client, bot, movie)
            except asyncio.TimeoutError:
                print(f"No reply from the bot in {REPLY_TIMEOUT}s on {code}. Is it running "
                      "the restore handler? Fix it and re-run `send`; progress is kept.")
                break
            except RPCError as e:
                reply = f"<telegram error: {e}>"

            if reply in (RESTORED_TEXT.format(code=code), ALREADY_EXISTS_TEXT.format(code=code)):
                done_file.write(code + "\n")
                done_file.flush()
                consecutive_failures = 0
                print(f"[{index}/{len(todo)}] {code}: {reply}")
            else:
                failed.append(code)
                consecutive_failures += 1
                print(f"[{index}/{len(todo)}] {code}: FAILED -> {reply}")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(f"{MAX_CONSECUTIVE_FAILURES} failures in a row, stopping.")
                    break

            if index < len(todo):
                await asyncio.sleep(delay + random.uniform(0, 1))

    if failed:
        print(f"Failed ({len(failed)}): {', '.join(failed)}")


async def run(args: argparse.Namespace) -> None:
    client = TelegramClient(args.session, int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
    # First run asks for the admin's phone number, login code and 2FA password.
    async with client:
        bot = await client.get_entity(args.bot)
        if args.command == "scan":
            await scan(client, bot)
        else:
            await send(client, bot, args.delay, args.limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore movies from the admin's chat with the bot.")
    parser.add_argument("command", choices=("scan", "send"))
    parser.add_argument("--bot", required=True, help="bot @username")
    parser.add_argument("--delay", type=float, default=5.0, help="seconds between sends (default 5)")
    parser.add_argument("--limit", type=int, default=None, help="send at most N movies")
    parser.add_argument("--session", default="admin", help="Telethon session file name")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
