import os
import sys
import calendar
from datetime import date
import requests

FOOTBALL_DATA_API_KEY = os.environ["FOOTBALL_DATA_API_KEY"]
GPT_API_KEY = os.environ["GPT_API_KEY"]
NTFY_TOPIC = os.environ["NTFY_TOPIC"]

# Man United's team ID on football-data.org
TEAM_ID = 66


def get_upcoming_month_range():
    """Return (date_from, date_to) strings for the next calendar month."""
    today = date.today()
    if today.month == 12:
        year, month = today.year + 1, 1
    else:
        year, month = today.year, today.month + 1

    last_day = calendar.monthrange(year, month)[1]
    date_from = date(year, month, 1).isoformat()
    date_to = date(year, month, last_day).isoformat()
    return date_from, date_to, year, month


def fetch_fixtures(date_from, date_to):
    url = f"https://api.football-data.org/v4/teams/{TEAM_ID}/matches"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    params = {"dateFrom": date_from, "dateTo": date_to, "status": "SCHEDULED"}

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("matches", [])


def format_fixtures_with_gpt(matches, year, month):
    month_name = calendar.month_name[month]

    if not matches:
        return f"No scheduled Manchester United fixtures found for {month_name} {year} yet. Check back closer to the month."

    # Build a simple raw listing to hand to GPT
    raw_lines = []
    for m in matches:
        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]
        utc_date = m["utcDate"]  # ISO 8601, e.g. 2026-09-13T14:00:00Z
        competition = m.get("competition", {}).get("name", "")
        raw_lines.append(f"{utc_date} | {home} vs {away} | {competition}")

    raw_text = "\n".join(raw_lines)

    prompt = f"""Here is a raw list of Manchester United fixtures for {month_name} {year}.
Each line is: UTC datetime | Home vs Away | Competition

{raw_text}

Format this into a clean, copy-paste-friendly list for a wallpaper/personal reference.
Convert each UTC datetime to a readable local date and time format like "Sat 13 Sep - 15:00 UK".
Assume UK time (BST/GMT as appropriate for the date) unless told otherwise.
One fixture per line, format: "DD Mon (Day) - HH:MM UK - Opponent (H/A) - Competition"
Sort chronologically. Add a title line at the top: "Manchester United Fixtures - {month_name} {year}".
Return ONLY the formatted list, no extra commentary."""

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
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def send_ntfy(message, year, month):
    month_name = calendar.month_name[month]
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    headers = {
        "Title": f"MUFC Fixtures - {month_name} {year}".encode("utf-8"),
        "Priority": "default",
        "Tags": "soccer",
    }
    resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=30)
    resp.raise_for_status()


def main():
    date_from, date_to, year, month = get_upcoming_month_range()
    print(f"Fetching fixtures from {date_from} to {date_to}")

    matches = fetch_fixtures(date_from, date_to)
    print(f"Found {len(matches)} scheduled matches")

    formatted = format_fixtures_with_gpt(matches, year, month)
    print("---- Formatted output ----")
    print(formatted)
    print("---------------------------")

    send_ntfy(formatted, year, month)
    print("Notification sent.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
