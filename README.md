# VoydodMovieBot

Telegram bot (`@Voydodfilmbot`) that distributes movies via unique codes behind
a mandatory channel-subscription gate, plus an admin panel for managing movies
and channels.

## Stack

Python 3.11 · aiogram 3.x · SQLAlchemy (async) · PostgreSQL · Docker Compose.

The bot uses long polling: it connects out to Telegram and listens on no port,
so it needs no domain, web server or TLS certificate.

## Configuration

Copy `.env.example` to `.env` and fill in the values:

| Variable | Purpose |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token |
| `ADMIN_IDS` | Comma-separated admin Telegram user IDs |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Database credentials (used by the db service) |
| `DATABASE_URL` | Async SQLAlchemy connection string; must match the three above |

Only one copy of the bot may run per token: a second poller makes Telegram
return conflicts to both.

## Run

```bash
docker compose up -d --build
docker compose logs -f bot
```

## Admin panel (`/admin`)

The dashboard exposes inline buttons:

- **📊 Statistika** — aggregate stats
- **🎬 Film qo'shish** — upload a movie (video → code → metadata)
- **📢 Kanal qo'shish / ❌ Kanal o'chirish** — manage mandatory channels

## Production

Runs on the shared server `deploy@159.195.213.245` in `/opt/voydodmoviebot`
(compose project `voydodmoviebot`). Other projects share that box: never run
`docker system prune -a` or anything with `--volumes` there.

Deploy an update:

```bash
cd /opt/voydodmoviebot && git pull && docker compose up -d --build
```

Backups: `scripts/backup_db.sh` runs nightly from the deploy user's crontab and
keeps 14 verified dumps in `/var/backups/voydodmoviebot/` (log: `backup.log`
there). Restore one into a fresh database with:

```bash
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < /var/backups/voydodmoviebot/voydod-XXXX.dump
```

## Restoring movies after losing the database

Uploaded videos stay on Telegram's servers, so a lost database can be rebuilt
from the admin's private chat with the bot. `scripts/restore_movies.py` logs in
as that admin (Telethon user session), pairs each `✅ Film qo'shildi!`
confirmation with its video, and re-sends the video to the bot **by reference**
(no download or re-upload) with a `#restore {json}` caption.
`app/handlers/restore.py` saves it under the bot's `file_id`.

1. Deploy this bot version (same `BOT_TOKEN`) and keep it running.
2. Get `api_id` / `api_hash` for the admin account at https://my.telegram.org.
3. Run, on any machine:

```bash
pip install -r scripts/requirements.txt
export TG_API_ID=... TG_API_HASH=...
python scripts/restore_movies.py scan --bot @Voydodfilmbot          # read-only, writes restore_plan.json
python scripts/restore_movies.py send --bot @Voydodfilmbot --limit 3  # test run
python scripts/restore_movies.py send --bot @Voydodfilmbot            # the rest, 5s apart
```

`send` is resumable (`restore_done.txt`) and marks a movie done only once the
bot replies. Do not clear the admin's chat with the bot until it finishes.
Delete `admin.session` afterwards; it grants full access to the account.

Only movies come back this way. Users, download counts and the required
channels are not in the chat history: re-add the channels in `/admin`.
