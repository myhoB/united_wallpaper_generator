import os
import sys
import time
import json
import calendar
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
import requests

LOCAL_TZ = ZoneInfo("Europe/Bratislava")

FOOTBALL_DATA_API_KEY = os.environ["FOOTBALL_DATA_API_KEY"]
GPT_API_KEY = os.environ["GPT_API_KEY"]
NTFY_TOPIC = os.environ["NTFY_TOPIC"]

# Man United's team ID on football-data.org
TEAM_ID = 66


def get_date_range():
    """Return (date_from, date_to) covering the full current month and full next month."""
    today = date.today()
    if today.month == 12:
        next_year, next_month = today.year + 1, 1
    else:
        next_year, next_month = today.year, today.month + 1

    last_day = calendar.monthrange(next_year, next_month)[1]
    date_from = date(today.year, today.month, 1).isoformat()
    date_to = date(next_year, next_month, last_day).isoformat()
    return date_from, date_to


EXCLUDED_STATUSES = {"POSTPONED", "SUSPENDED", "CANCELLED"}


def fetch_fixtures(date_from, date_to):
    url = f"https://api.football-data.org/v4/teams/{TEAM_ID}/matches"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    params = {"dateFrom": date_from, "dateTo": date_to}

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    matches = data.get("matches", [])

    return [m for m in matches if m.get("status") not in EXCLUDED_STATUSES]


def shorten_name(name):
    return name.replace("Manchester", "Man.")


def to_local(utc_date_str):
    dt_utc = datetime.strptime(utc_date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(LOCAL_TZ)


SNAPSHOT_FILE = "last_fixtures.json"

def load_snapshot():
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE) as f:
            return json.load(f)
    return {}

def save_snapshot(matches):
    snapshot = {str(m["id"]): m["utcDate"] for m in matches}
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(snapshot, f, indent=2)

def fixtures_changed(matches, previous_snapshot):
    current = {str(m["id"]): m["utcDate"] for m in matches}
    return current != previous_snapshot


def format_fixtures_plain(matches):
    """Fallback formatter that doesn't need any AI call."""
    lines = []

    sorted_matches = sorted(matches, key=lambda m: m["utcDate"])
    for m in sorted_matches:
        home = shorten_name(m["homeTeam"]["name"])
        away = shorten_name(m["awayTeam"]["name"])
        competition = m.get("competition", {}).get("name", "")
        local_dt = to_local(m["utcDate"])

        lines.append(f"{local_dt.strftime('%a %-d %b')} | {competition}")
        lines.append(f"{home} vs. {away}")
        lines.append(f"time {local_dt.strftime('%H:%M')}")
        lines.append("")  # blank line between fixtures

    return "\n".join(lines).strip()


def format_fixtures_with_gpt(matches, max_retries=3):
    if not matches:
        return "No scheduled Manchester United fixtures found for this month or next month yet. Check back later."

    # Build a raw listing with LOCAL times already computed (do not let the model
    # do timezone math itself — compute it here and just have GPT arrange it)
    raw_lines = []
    for m in matches:
        home = shorten_name(m["homeTeam"]["name"])
        away = shorten_name(m["awayTeam"]["name"])
        local_dt = to_local(m["utcDate"])
        competition = m.get("competition", {}).get("name", "")
        raw_lines.append(
            f"{local_dt.strftime('%a %-d %b')} | {competition} | {home} vs. {away} | time {local_dt.strftime('%H:%M')}"
        )

    raw_text = "\n".join(raw_lines)

    prompt = f"""Here is a list of Manchester United fixtures covering the remainder of this month and all of next month, with times already converted to local Slovak time.
Each line is: Day DateMonth | Competition | Home vs. Away | time HH:MM

{raw_text}

Reformat each fixture into EXACTLY this 3-line layout, with a blank line between fixtures:
Day DateMonth | Competition
Home vs. Away
time HH:MM

Example:
Sun 6 Sep | Premier League
Man. City vs. Man. United
time 16:00

Keep the day/date/time and team names exactly as given (do not alter them). Sort chronologically.
Return ONLY the formatted list, no title, no extra commentary."""

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GPT_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
                timeout=60,
            )
            if resp.status_code == 429:
                wait = 2 ** attempt  # 2s, 4s, 8s
                print(f"GPT rate-limited (attempt {attempt}/{max_retries}), waiting {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.RequestException as e:
            print(f"GPT call failed (attempt {attempt}/{max_retries}): {e}")
            time.sleep(2 ** attempt)

    print("GPT formatting failed after retries — falling back to plain formatting.")
    return format_fixtures_plain(matches)


def send_ntfy(message):
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    headers = {
        "Title": "MUFC Fixtures - This & Next Month".encode("utf-8"),
        "Priority": "default",
        "Tags": "soccer",
    }
    resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=30)
    resp.raise_for_status()


def main():
    date_from, date_to = get_date_range()
    print(f"Fetching fixtures from {date_from} to {date_to}")

    matches = fetch_fixtures(date_from, date_to)
    print(f"Found {len(matches)} scheduled matches")

    previous = load_snapshot()
    if not fixtures_changed(matches, previous):
        print("No fixture changes detected — skipping notification.")
        return

    formatted = format_fixtures_with_gpt(matches)
    print("---- Formatted output ----")
    print(formatted)
    print("---------------------------")

    send_ntfy(formatted)
    print("Notification sent.")

    save_snapshot(matches)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
