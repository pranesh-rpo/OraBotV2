# Ora Ads Bot

Ora Ads Bot is an Aiogram + Telethon based system for broadcasting messages to Telegram groups from linked accounts. It supports safe-rate broadcasting, account management, scheduling in IST, logging, and admin monitoring.

## Features
- Link multiple Telegram accounts via OTP and optional 2FA
- Auto-fetch and cache joined groups for each account
- Broadcast to groups with flood-wait and permission handling
- Smart timing: default ~5 messages/hour or manual intervals
- Schedule windows in IST with auto start/stop
- Per-account logs stored in SQLite and optionally sent to admins via a logger bot
- Single-instance lock to prevent duplicate bot runs

## Quick Start
1. Install Python `3.11+` (see `runtime.txt`).
2. Create and activate a virtual environment.
3. Install dependencies.
4. Configure environment.
5. Run the bot.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # if you have a template; otherwise create .env
# Edit .env with your values
python3 main.py
```

Alternatively, use the manager script:

```bash
./bot_manager.sh start
./bot_manager.sh stop
./bot_manager.sh status
```

## Environment Variables
Defined and validated in `config.py`.

Required:
- `BOT_TOKEN`: Telegram bot token
- `API_ID`: Telegram API ID
- `API_HASH`: Telegram API hash
- `VERIFICATION_CHANNEL_ID`: Numeric ID of the verification channel
- `ENCRYPTION_KEY`: Secret key used to encrypt Telethon session strings

Optional:
- `BOT_USERNAME`: Bot username label (UI only)
- `APP_VERSION`: Version label
- `DATABASE_PATH`: Path to SQLite DB (default `./data/ora_ads.db`)
- `VERIFICATION_CHANNEL`: Public handle of verification channel (used in UI)
- `LOGGER_BOT_TOKEN`: Bot token for external logger bot (sends logs to admins/users)
- `ADMIN_IDS`: Comma-separated admin chat IDs (receive external logs)

## Running & Workflow
- Start the bot (`main.py`) which:
  - Validates config and initializes the database
  - Registers routers and starts polling
  - Starts the scheduler task for auto start/stop
- Interact with the bot:
  - `/start` → join verification and open main menu
  - Link account → enter phone, OTP, and 2FA if needed
  - Manage accounts → set message, interval, schedule, join groups, view logs
  - Start/Stop broadcast per account

## Scheduling (IST)
- Set a schedule via the account dashboard `🕐 Set Schedule`:
  - The bot asks for broadcast message → start time → end time (HH:MM, 24-hour)
  - Times are interpreted in IST (UTC+05:30)
- Auto behavior:
  - If current time is inside the window, broadcast starts immediately
  - A background scheduler checks each minute and auto starts/stops the broadcast per account based on the schedule window
- Manual interval:
  - If you set a manual interval (`⏱️ Set Interval`), broadcasts use that fixed spacing
  - Otherwise, default ~5 messages/hour timing applies

## Broadcast Behavior
- Uses Telethon clients per linked account
- Iterates over cached groups and sends messages sequentially
- Handles `FloodWait`, `ChatWriteForbidden`, `UserBannedInChannel`, `ChatAdminRequired` gracefully
- Marks inactive groups in DB when writing isn’t allowed or IDs are invalid
- Refreshes the group list each cycle to stay up-to-date

## Logs
- Stored in SQLite with IST timestamps
- View logs per account via UI
- Optional external logs via `LOGGER_BOT_TOKEN` sent to `ADMIN_IDS` and optionally the user

## Project Structure & File Guide

Top-level:
- `main.py`: Entry point. Config validation, DB init, router registration, polling, scheduler start/stop.
- `config.py`: Loads env vars, defines defaults, validates required configs, sets broadcast timing defaults.
- `requirements.txt`: Python dependencies.
- `runtime.txt`: Target Python version.
- `bot_manager.sh`: Helper script for start/stop/status with venv bootstrap.
- `data/ora_ads.db`: Default SQLite database (path configurable).

App module:
- `app/bot/handlers_start.py`: `/start`, verification, main menu navigation.
- `app/bot/handlers_account.py`: Account management flows:
  - Link new account (phone → OTP → 2FA), delete account
  - Set message, set manual interval, join groups, view logs
  - Toggle broadcast start/stop and show account dashboard
- `app/bot/keyboards.py`: Inline keyboards for menus and actions.
- `app/bot/menus.py`: Rich text templates for instructional and status messages.

Client:
- `app/client/session_manager.py`: Create/load/disconnect Telethon clients, send code, sign in, fetch dialogs.
- `app/client/broadcast_worker.py`: Core broadcast loop per account:
  - Reads message, groups, and schedule/interval from DB
  - Respects IST schedule windows and smart delays
  - Refreshes groups and handles errors/flood waits
  - Updates logs and `is_broadcasting` status

Scheduler:
- `app/scheduler/schedule_handlers.py`: UI flow to set message and schedule window (IST), immediate auto-start if inside window.
- `app/scheduler/task_manager.py`: Background task that checks each minute and auto starts/stops broadcasts per active schedule.
- `app/scheduler/random_scheduler.py`: Placeholder for any alternative/randomized scheduling strategies.

Database:
- `app/database/models.py`: Creates tables on startup (`users`, `accounts`, `messages`, `schedules`, `logs`, `groups`).
- `app/database/operations.py`: High-level DB operations (add accounts, save messages, set/get schedules, logs, groups, intervals).

Utilities:
- `app/utils/anti_spam.py`: Randomized delays and safe-send helper to minimize flood risk.
- `app/utils/encryption.py`: Encrypts/decrypts Telethon session strings using `ENCRYPTION_KEY`.
- `app/utils/lock.py`: Single-instance OS lock to prevent multiple bot instances.
- `app/utils/logger.py`: External logger bot integration for sending formatted logs to admins/users.
- `app/utils/validators.py`: Input validators (if any additional checks are implemented).

Data flow overview:
1. User links an account → session saved encrypted in DB → groups fetched and cached
2. User sets message and schedule/interval
3. User starts broadcast (or auto-start via schedule)
4. Broadcast worker loops through groups, sends messages, logs activity, and sleeps according to timing mode
5. Scheduler ensures broadcast runs only inside IST windows

## Database Schema (Summary)
- `users(user_id, username, first_name, joined_at, is_verified, is_active)`
- `accounts(id, user_id, phone_number, session_string, first_name, is_active, is_broadcasting, manual_interval, created_at)`
- `messages(id, account_id, message_text, is_active, created_at, updated_at)`
- `schedules(id, account_id, start_time, end_time, min_interval, max_interval, is_active)`
- `logs(id, account_id, log_type, message, status, timestamp)`
- `groups(id, account_id, group_id, group_title, last_message_sent, is_active)`

## Troubleshooting
- Missing config: Check `.env` and `config.py.validate()` requirements.
- FloodWaits: The worker logs waits and continues; reduce rate or widen intervals.
- No groups: Ensure account joined groups; run refresh in UI or re-link.
- Session expired: Re-link the account to obtain a new session string.
- Permission errors: The bot can’t post where writing is forbidden; those groups are marked inactive.

## Security Notes
- Never commit real `.env` values. Keep `BOT_TOKEN`, `API_ID`, `API_HASH`, and `ENCRYPTION_KEY` secret.
- Session strings are encrypted at rest using your `ENCRYPTION_KEY`.

## Contributing
- Follow existing patterns in handlers and worker code.
- Keep logs and timestamps in IST for consistency with UI.
- Avoid adding comments or secrets into the codebase.