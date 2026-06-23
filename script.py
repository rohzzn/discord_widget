# ╔══════════════════════════════════════════════════════════════════╗
# ║              DISCORD WIDGET UPDATER — rohan                     ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║  FILE: widget.py                                                 ║
# ║                                                                  ║
# ║  WHAT IT DOES:                                                   ║
# ║  Updates your Discord profile widget every 60 seconds with:     ║
# ║    - Cincinnati time                                             ║
# ║    - Spotify weekly top song                                     ║
# ║    - CS2 Premier rating (Leetify)                                ║
# ║    - Total GitHub commits                                        ║
# ║    - Last workout kg (Hevy)                                      ║
# ║    - Last rated movie (TMDB)                                     ║
# ║                                                                  ║
# ║  SETUP (Docker):                                                 ║
# ║    1. Copy .env.example → .env and fill in your keys            ║
# ║    2. docker compose up -d --build                               ║
# ║    3. docker compose logs -f                                     ║
# ║                                                                  ║
# ║  LOCAL (no Docker):                                              ║
# ║    pip install -r requirements.txt && python script.py           ║
# ║                                                                  ║
# ║  WIDGET EDITOR FIELD NAMES (Discord Developer Portal):          ║
# ║    Stat 1 → time          Stat 4 → commits                      ║
# ║    Stat 2 → song          Stat 5 → last_workout                 ║
# ║    Stat 3 → premier       Stat 6 → film                         ║
# ╚══════════════════════════════════════════════════════════════════╝

import os
import requests
import time
import base64
import random
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── CONFIG ────────────────────────────────────────────────────────────────────

def _require(name):
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


SPOTIFY_CLIENT_ID     = _require("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = _require("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REFRESH_TOKEN = _require("SPOTIFY_REFRESH_TOKEN")

LEETIFY_STEAM_ID      = _require("LEETIFY_STEAM_ID")
LEETIFY_API_KEY       = _require("LEETIFY_API_KEY")

GITHUB_USERNAME       = _require("GITHUB_USERNAME")

HEVY_API_KEY          = _require("HEVY_API_KEY")
HEVY_WORKOUT_DAYS     = int(os.getenv("HEVY_WORKOUT_DAYS", "7"))
HEVY_PAGE_SIZE        = int(os.getenv("HEVY_PAGE_SIZE", "10"))
HEVY_MAX_PAGES        = int(os.getenv("HEVY_MAX_PAGES", "5"))

TMDB_TOKEN            = _require("TMDB_TOKEN")
TMDB_SESSION_ID       = _require("TMDB_SESSION_ID")
TMDB_ACCOUNT_ID       = _require("TMDB_ACCOUNT_ID")

DISCORD_APP_ID        = _require("DISCORD_APP_ID")
DISCORD_BOT_TOKEN     = _require("DISCORD_BOT_TOKEN")
DISCORD_USER_ID       = _require("DISCORD_USER_ID")

EASTERN = ZoneInfo("America/New_York")  # Cincinnati = Eastern

RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
MAX_BACKOFF_SLEEP = 300


def _safe_json(response):
    try:
        return response.json()
    except ValueError:
        return {}


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _retry_after_seconds(response):
    body = _safe_json(response)
    retry_after = _as_float(response.headers.get("Retry-After"))
    if retry_after is None:
        retry_after = _as_float(body.get("retry_after"))
    if retry_after is None:
        retry_after = _as_float(response.headers.get("X-RateLimit-Reset-After"))
    if retry_after is None:
        reset_at = _as_float(response.headers.get("X-RateLimit-Reset"))
        if reset_at is not None:
            retry_after = max(0, reset_at - time.time())
    if retry_after is None:
        retry_after = 5
    return max(0, retry_after) + 1


def _backoff_seconds(attempt):
    return min(MAX_BACKOFF_SLEEP, (2 ** (attempt - 1)) + random.uniform(0, 0.5))


def request_with_retries(method, url, *, name="HTTP", retries=4, session=None, **kwargs):
    client = session or requests
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            response = client.request(method, url, **kwargs)
        except requests.RequestException as e:
            last_error = e
            if attempt == retries:
                break
            wait = _backoff_seconds(attempt)
            print(f"  [WARN] {name}: {e} (attempt {attempt}/{retries}) - retrying in {wait:.1f}s")
            time.sleep(wait)
            continue

        if response.status_code not in RETRYABLE_STATUSES or attempt == retries:
            return response

        if response.status_code == 429:
            wait = _retry_after_seconds(response)
            scope = response.headers.get("X-RateLimit-Scope", "unknown")
            print(f"  [WARN] {name}: rate limited ({scope}, attempt {attempt}/{retries}) - waiting {wait:.1f}s")
        else:
            wait = _backoff_seconds(attempt)
            print(f"  [WARN] {name}: HTTP {response.status_code} (attempt {attempt}/{retries}) - retrying in {wait:.1f}s")
        time.sleep(wait)

    raise requests.RequestException(f"{name} request failed after {retries} attempts: {last_error}")

# ── WIDGET FIELDS (must match exactly in Discord widget editor) ───────────────
# Stat 1: time
# Stat 2: song
# Stat 3: premier
# Stat 4: commits
# Stat 5: last_workout
# Stat 6: film

# ── SOURCES ───────────────────────────────────────────────────────────────────

def get_time():
    now  = datetime.now(EASTERN)
    h    = now.hour % 12 or 12
    m    = now.strftime("%M")
    ampm = "AM" if now.hour < 12 else "PM"
    return f"{h}:{m} {ampm}"


def get_spotify_token():
    creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    r = request_with_retries(
        "POST",
        "https://accounts.spotify.com/api/token",
        name="Spotify token",
        headers={"Authorization": f"Basic {creds}"},
        data={"grant_type": "refresh_token", "refresh_token": SPOTIFY_REFRESH_TOKEN},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def get_top_song(token):
    r = request_with_retries(
        "GET",
        "https://api.spotify.com/v1/me/top/tracks?time_range=short_term&limit=1",
        name="Spotify top tracks",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    r.raise_for_status()
    items = r.json().get("items", [])
    if not items:
        return "N/A"
    track = items[0]
    return track["name"]


def get_premier():
    r = request_with_retries(
        "GET",
        f"https://api.leetify.com/api/mini-profiles/{LEETIFY_STEAM_ID}",
        name="Leetify",
        headers={"x-api-key": LEETIFY_API_KEY},
        timeout=10,
    )
    r.raise_for_status()
    for rank in r.json().get("ranks", []):
        if rank.get("type") == "premier":
            return str(rank["skillLevel"])
    return "N/A"


def get_commits():
    r = request_with_retries(
        "GET",
        f"https://github-contributions-api.jogruber.de/v4/{GITHUB_USERNAME}",
        name="GitHub contributions",
        timeout=10,
    )
    if r.ok:
        return str(sum(r.json().get("total", {}).values()))
    return "N/A"


def _parse_hevy_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _workout_time(workout):
    if not isinstance(workout, dict):
        return None
    for key in ("start_time", "end_time", "created_at", "updated_at"):
        dt = _parse_hevy_time(workout.get(key))
        if dt is not None:
            return dt
    return None


def _workout_day(workout):
    workout_at = _workout_time(workout)
    if workout_at is None:
        return None
    return workout_at.astimezone(EASTERN).date()


def _set_volume_kg(workout_set):
    if not isinstance(workout_set, dict):
        return 0
    weight = _as_float(workout_set.get("weight_kg")) or 0
    reps = _as_float(workout_set.get("reps")) or 0
    return weight * reps


def _workout_volume_kg(workout):
    if not isinstance(workout, dict):
        return 0
    total = 0.0
    for ex in workout.get("exercises") or []:
        if not isinstance(ex, dict):
            continue
        for s in ex.get("sets") or []:
            total += _set_volume_kg(s)
    return total


def get_last_workout():
    totals_by_day = {}

    for page in range(1, HEVY_MAX_PAGES + 1):
        r = request_with_retries(
            "GET",
            f"https://api.hevyapp.com/v1/workouts?page={page}&pageSize={HEVY_PAGE_SIZE}",
            name="Hevy",
            headers={"api-key": HEVY_API_KEY},
            timeout=15,
        )
        r.raise_for_status()
        workouts = r.json().get("workouts", [])
        if not workouts:
            break

        page_days = []
        for workout in workouts:
            workout_day = _workout_day(workout)
            if workout_day is None:
                continue
            page_days.append(workout_day)
            totals_by_day[workout_day] = totals_by_day.get(workout_day, 0) + _workout_volume_kg(workout)

        selected_days = sorted(totals_by_day, reverse=True)[:HEVY_WORKOUT_DAYS]
        if len(selected_days) >= HEVY_WORKOUT_DAYS and any(day < selected_days[-1] for day in page_days):
            break

    selected_days = sorted(totals_by_day, reverse=True)[:HEVY_WORKOUT_DAYS]
    if not selected_days:
        return "N/A"

    total = sum(totals_by_day[day] for day in selected_days)
    return f"{total:,.0f} kg"


def get_last_watched():
    r = request_with_retries(
        "GET",
        f"https://api.themoviedb.org/3/account/{TMDB_ACCOUNT_ID}/rated/movies"
        f"?session_id={TMDB_SESSION_ID}&sort_by=created_at.desc&page=1",
        name="TMDB",
        headers={"Authorization": f"Bearer {TMDB_TOKEN}"},
        timeout=10,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        return "N/A"
    m = results[0]
    year = m.get("release_date", "")[:4]
    return f"{m['title']} ({year})"


# ── DISCORD ───────────────────────────────────────────────────────────────────

_session = requests.Session()
_session.headers.update({
    "Content-Type": "application/json",
    "Authorization": f"Bot {DISCORD_BOT_TOKEN}",
    "User-Agent": "DiscordBot (https://github.com/discord/discord-api-docs, 1.0.0)",
})
WIDGET_URL = (
    f"https://discord.com/api/v9/applications/{DISCORD_APP_ID}"
    f"/users/{DISCORD_USER_ID}/identities/0/profile"
)
_discord_reset_at = 0


def _wait_for_discord_bucket():
    wait = _discord_reset_at - time.time()
    if wait > 0:
        print(f"  Discord bucket cooling down - waiting {wait:.1f}s")
        time.sleep(wait)


def _remember_discord_bucket(response):
    global _discord_reset_at
    if response.headers.get("X-RateLimit-Remaining") == "0":
        _discord_reset_at = max(_discord_reset_at, time.time() + _retry_after_seconds(response))


def push(fields: dict):
    payload = {
        "username": GITHUB_USERNAME,
        "data": {"dynamic": [{"type": 1, "name": k, "value": v} for k, v in fields.items()]},
    }

    try:
        _wait_for_discord_bucket()
        r = request_with_retries(
            "PATCH",
            WIDGET_URL,
            name="Discord",
            retries=4,
            session=_session,
            json=payload,
            timeout=10,
        )
    except requests.RequestException as e:
        print(f"  [ERROR] Discord request failed: {e}")
        return False

    _remember_discord_bucket(r)
    if r.ok:
        return True

    if r.status_code == 429:
        wait = _retry_after_seconds(r)
        print(f"  rate limited after retries - retrying next cycle after {wait:.1f}s")
        return False

    print(f"  [ERROR] Discord {r.status_code}: {r.text}")
    return False


# ── MAIN ──────────────────────────────────────────────────────────────────────

def run_loop(fast=60, slow=600):
    """
    fast: seconds between each Discord push (Spotify top song + time)
    slow: seconds between refreshing heavy sources (GitHub, Leetify, Hevy, TMDB)
    """
    print("Discord Widget — starting\n")
    print("Field names for widget editor:")
    print("  Stat 1 : time")
    print("  Stat 2 : song")
    print("  Stat 3 : premier")
    print("  Stat 4 : commits")
    print("  Stat 5 : last_workout")
    print("  Stat 6 : film\n")

    cache = {
        "premier":      "...",
        "commits":      "...",
        "last_workout": "...",
        "last_watched": "...",
        "last_slow":    0,
    }

    while True:
        now = time.time()

        # Refresh slow sources every 10 min
        if now - cache["last_slow"] > slow:
            print("  [slow refresh] GitHub, Leetify, Hevy, TMDB...")
            for name, fn in [
                ("premier",      get_premier),
                ("commits",      get_commits),
                ("last_workout", get_last_workout),
                ("last_watched", get_last_watched),
            ]:
                try:
                    cache[name] = fn()
                    print(f"    {name}: {cache[name]}")
                except Exception as e:
                    print(f"    [WARN] {name}: {e}")
            cache["last_slow"] = time.time()

        # Fast sources every tick
        cin_time = get_time()
        top_song = "N/A"
        try:
            token    = get_spotify_token()
            top_song = get_top_song(token)
        except Exception as e:
            print(f"  [WARN] Spotify: {e}")

        fields = {
            "time":         cin_time,
            "song":         top_song,
            "premier":      cache["premier"],
            "commits":      cache["commits"],
            "last_workout": cache["last_workout"],
            "film":         cache["last_watched"],
        }

        ok = push(fields)
        if ok:
            print(f"[OK] {cin_time} | {top_song} | Premier {cache['premier']} | "
                  f"{cache['commits']} commits | {cache['last_workout']} | {cache['last_watched']}")

        time.sleep(fast)


if __name__ == "__main__":
    run_loop(
        fast=int(os.getenv("LOOP_FAST_SECONDS", "60")),
        slow=int(os.getenv("LOOP_SLOW_SECONDS", "7200")),
    )