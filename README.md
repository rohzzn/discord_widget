# Discord Profile Widget Updater

A lightweight background service that keeps a Discord profile widget in sync with live personal stats. It polls external APIs on a schedule and pushes updates to Discord's widget profile endpoint.

> **New to Discord widgets?** Start with the full setup guide: [How to Build Discord Profile Widgets](https://www.rohan.run/writing/discord-widgets). That walkthrough covers the Developer Portal, OAuth, bot tokens, and publishing your widget layout. This repository is the runtime that keeps your widget data fresh after that initial setup.

## What it updates

| Stat | Source | Refresh interval |
|------|--------|------------------|
| Local time (Eastern) | System clock | Every 60s |
| Top Spotify track | Spotify Web API | Every 60s |
| CS2 Premier rating | Leetify | Every 2 hours |
| Total GitHub commits | GitHub contributions API | Every 2 hours |
| Recent workout volume | Hevy | Every 2 hours |
| Last rated film | TMDB | Every 2 hours |

Intervals are configurable via `LOOP_FAST_SECONDS` and `LOOP_SLOW_SECONDS` in `.env`.

## Widget field mapping

When building your widget in the Discord Developer Portal, use these **User Data** field names so they match what this script sends:

| Widget stat | Data field name |
|-------------|-----------------|
| Stat 1 | `time` |
| Stat 2 | `song` |
| Stat 3 | `premier` |
| Stat 4 | `commits` |
| Stat 5 | `last_workout` |
| Stat 6 | `film` |

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (recommended)
- A Discord application with widgets enabled — see the [setup guide](https://www.rohan.run/writing/discord-widgets)
- API credentials for the services you want to display

## Quick start (Docker)

1. **Complete Discord widget setup** using [How to Build Discord Profile Widgets](https://www.rohan.run/writing/discord-widgets). You need your application ID, bot token, user ID, and a published widget layout before this service will do anything useful.

2. **Configure environment variables:**

   ```bash
   cp .env.example .env
   ```

   Fill in `.env` with your credentials. Never commit this file.

3. **Start the service:**

   ```bash
   docker compose up -d --build
   ```

4. **Verify it is running:**

   ```bash
   docker compose logs -f
   ```

   You should see periodic `[OK]` lines with the current stat values. The container restarts automatically on failure and when Docker starts (`restart: unless-stopped`).

## Local development

If you prefer to run without Docker:

```bash
pip install -r requirements.txt
python script.py
```

The script loads configuration from `.env` in the project root.

## Configuration

All settings are read from environment variables. See `.env.example` for the full list.

| Variable | Description |
|----------|-------------|
| `DISCORD_APP_ID` | Discord application ID |
| `DISCORD_BOT_TOKEN` | Bot token from the Developer Portal |
| `DISCORD_USER_ID` | Your Discord user ID |
| `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET` / `SPOTIFY_REFRESH_TOKEN` | Spotify API credentials |
| `LEETIFY_STEAM_ID` / `LEETIFY_API_KEY` | Leetify CS2 stats |
| `GITHUB_USERNAME` | GitHub username for commit totals |
| `HEVY_API_KEY` | Hevy workout API key |
| `TMDB_TOKEN` / `TMDB_SESSION_ID` / `TMDB_ACCOUNT_ID` | TMDB rated movies |
| `LOOP_FAST_SECONDS` | Seconds between time, song, and Discord pushes (default: `60`) |
| `LOOP_SLOW_SECONDS` | Seconds between heavy source refreshes (default: `7200`) |

## Operations

```bash
# Start in the background
docker compose up -d --build

# Stream logs
docker compose logs -f

# Stop
docker compose down

# Rebuild after code or dependency changes
docker compose up -d --build

# Restart after .env changes
docker compose up -d --force-recreate
```

## Project structure

```
discord_widget/
├── script.py           # Main updater loop
├── docker-compose.yml  # Service definition
├── Dockerfile
├── requirements.txt
├── .env.example        # Configuration template
└── README.md
```

## Notes

- Discord's widget API is experimental. Rate limits are handled with retries and backoff, but avoid setting `LOOP_FAST_SECONDS` too low.
- This project is intended for **personal use** (single user, application identity `0`). For a multi-user service, see the bot-based pattern in the [setup guide](https://www.rohan.run/writing/discord-widgets#05widget-management-with-a-bot).
- Keep `.env` out of version control. Rotate any credentials that may have been exposed.

## License

Personal project. Use and adapt as you like.
