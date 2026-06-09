Technical Specification: Telegram Movie Retrieval Bot
1. Project Overview & Constraints

    Objective: Develop a Telegram bot that distributes movies via unique codes, gated by a mandatory channel subscription system.

    Stack: Python 3.11+, aiogram 3.x, PostgreSQL (asyncpg or SQLAlchemy), Docker / Docker Compose.

    Media Handling: Strictly NO media downloads/storage. All media must be handled via Telegram's native file_id.

    Deployment: Containerized backend utilizing Docker Compose for the bot application and PostgreSQL database.

2. Database Schema (PostgreSQL)

The AI agent should implement the following tables using SQLAlchemy ORM (async) or raw SQL via asyncpg.

    users

        id (BigInt, Primary Key) - Telegram User ID

        username (String, Nullable)

        full_name (String)

        is_verified (Boolean, Default: False) - Passed mandatory sub check

        created_at (Timestamp)

        last_active (Timestamp)

    channels (Mandatory subscription list)

        id (Integer, Primary Key)

        channel_id (BigInt, Unique) - Internal Telegram Chat ID

        channel_username (String, Unique) - e.g., @kinohudud

        title (String) - For button display

        added_at (Timestamp)

    movies

        id (Integer, Primary Key)

        code (String, Unique, Index) - The numeric code from Instagram Reels

        file_id (String) - Telegram Video File ID

        title (String) - e.g., "Qora libosli odamlar 3"

        country (String) - e.g., "AQSh"

        year (Integer) - e.g., 2013

        language (String) - e.g., "O'zbek tilida"

        genre (String) - e.g., "Fantastika jangari"

        download_count (Integer, Default: 0)

    activity_logs (For Admin Panel stats)

        id (Integer, Primary Key)

        user_id (BigInt, ForeignKey to users.id)

        action (String) - e.g., "REQUESTED_MOVIE", "VERIFIED_SUBSCRIPTION"

        target_id (String, Nullable) - e.g., the movie code requested

        timestamp (Timestamp)

3. Core Application Flows
Flow A: User Onboarding & Forced Subscription

    Trigger: User sends /start.

    Logic:

        Upsert user into the users table.

        Query channels table. If channels is empty, auto-verify user and proceed to Flow B.

        If channels exist, generate an Inline Keyboard.

    UI Components:

        N buttons (one for each channel) linking to the channel URLs.

        1 bottom button: ✅ Tasdiqlash (Callback data: verify_subs).

    Verification Logic (verify_subs callback):

        Bot iterates through the channels list and calls bot.get_chat_member(chat_id=channel.id, user_id=user.id).

        Success Condition: Member status is member, administrator, or creator for ALL channels.

        Pass: Update is_verified = True in DB. Send success message: "✅ Tasdiqlandi! Botdan foydalanishingiz mumkin. Film kodini yozing:".

        Fail: Answer callback query with an alert: "Iltimos, barcha kanallarga obuna bo'ling!" (Please subscribe to all channels).

Flow B: Movie Retrieval

    Trigger: User sends a text message (the code).

    Middleware/Check: Assert is_verified == True. If false, trigger Flow A.

    Logic:

        Validate text is numeric/alphanumeric (based on your code format).

        Query movies table where code == user_text.

    Output (Success):

        Increment download_count for that movie.

        Log activity.

        Send video using file_id.

        Caption Template:
        Plaintext

        🎬 {title} | Kod - {code}
        — — — — — —
        🌐 • {country}
        📆 • {year}
        🎙 • {language}
        🎭 • {genre}
        © • @{bot_username}
        📥 • Yuklandi: {download_count}

    Output (Fail): Send "Kechirasiz, bunday kodli film topilmadi." (Sorry, movie with this code not found).

4. Admin Panel & FSM (Finite State Machine)

Access Control: The /admin command and all admin callbacks must be guarded by a middleware or decorator checking if user.id is in the ADMIN_IDS environment variable.
Admin Dashboard (/admin)

Displays a summary (Total Users, Total Movies, Total Downloads) and an Inline Keyboard:

    [ 📊 Statistika ]

    [ 🎬 Film qo'shish ] (Upload Movie)

    [ 📢 Kanal qo'shish ] (Add Channel)

    [ ❌ Kanal o'chirish ] (Remove Channel)

Admin Action: Add Channel (FSM)

    State 1: Bot asks admin to forward a message from the target channel OR send its @username.

    State 2: Bot processes the input.

        Crucial Check: Bot calls bot.get_chat_administrator_rights(chat_id). If the bot lacks admin rights, it rejects the addition and informs the admin: "Xatolik: Bot ushbu kanalda admin emas. Dastlab botni admin qiling." (Error: Bot is not an admin. Make bot admin first).

        Success: Save channel id, username, and title to the channels DB. Clear FSM. Send confirmation.

Admin Action: Upload Movie (FSM)

    State 1 (Video): Bot asks admin to send the video file.

        Action: Bot extracts message.video.file_id.

    State 2 (Code): Bot asks for the unique shortcode.

        Validation: Check if code already exists in DB.

    State 3 (Metadata): Bot sequentially asks for Title, Country, Year, Language, and Genre. (Can be implemented as single prompts or one formatted message parsing).

    Finalization: Save to movies table. Send a preview of the finished post to the admin. Clear FSM.

5. Docker Orchestration Strategy

To ensure a predictable environment, instruct the AI to generate a docker-compose.yml with the following services:

    db: PostgreSQL 15-alpine image. Expose port 5432. Map a volume for persistent data. Define POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB in .env.

    bot: Python 3.11-slim image. Build from local Dockerfile. Depend on db. Pass BOT_TOKEN, DATABASE_URL, and ADMIN_IDS as environment variables.