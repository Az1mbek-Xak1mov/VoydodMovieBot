# VoydodMovieBot

Telegram bot that distributes movies via unique codes behind a mandatory
channel-subscription gate, plus an admin panel for managing movies, channels,
and **AI image generation/editing** (Azure OpenAI `gpt-image-2`).

## Stack

Python 3.11 · aiogram 3.x · SQLAlchemy (async) · PostgreSQL · Docker Compose ·
Azure OpenAI (images).

## Configuration

Copy `.env.example` to `.env` and fill in the values:

| Variable | Purpose |
| --- | --- |
| `BOT_TOKEN` | Telegram bot token |
| `ADMIN_IDS` | Comma-separated admin Telegram user IDs |
| `DATABASE_URL` | Async SQLAlchemy connection string |
| `AZURE_OPENAI_ENDPOINT_IMAGE` | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_KEY_IMAGE` | Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT_IMAGE` | Image deployment name (e.g. `gpt-image-2`) |
| `AZURE_OPENAI_API_VERSION` | API version — must be `2025-04-01-preview` (older versions 404 on the Images Edit endpoint) |

## Run

```bash
docker compose up --build
```

## Admin panel (`/admin`)

The dashboard exposes inline buttons:

- **📊 Statistika** — aggregate stats
- **🎬 Film qo'shish** — upload a movie (video → code → metadata)
- **📢 Kanal qo'shish / ❌ Kanal o'chirish** — manage mandatory channels
- **🎨 Rasm yaratish** — generate an image from a text prompt
- **🖌 Rasmni tahrirlash** — edit/restyle images: send one or more reference
  images (up to 16), then send the edit prompt. The result is returned as a
  photo.

Image work runs through `app/services/image.py`, a thin async wrapper around the
Azure OpenAI `images.generate` / `images.edit` endpoints. Images are passed in
memory — nothing is written to disk.
