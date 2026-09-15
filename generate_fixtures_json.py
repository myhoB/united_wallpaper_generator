import os
import sys
import json
import calendar
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
import requests
from icalendar import Calendar

FOOTBALL_DATA_API_KEY = os.environ["FOOTBALL_DATA_API_KEY"]
TEAM_ID = 66
LOCAL_TZ = ZoneInfo("Europe/Bratislava")
EXCLUDED_STATUSES = {"POSTPONED", "SUSPENDED", "CANCELLED"}
OUTPUT_FILE = "docs/fixtures.json"

ICS_URL = "https://www.manutd.com/en/Manchester_United.ics"
ICS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def get_date_range():
    today = date.today()
    if today.month == 12:
        next_year, next_month = today.year + 1, 1
    else:
        next_year, next_month = today.year, today.month + 1

    last_day = calendar.monthrange(next_year, next_month)[1]
    date_from = date(today.year, today.month, 1).isoformat()
    date_to = date(next_year, next_month, last_day).isoformat()
    return date_from, date_to


def shorten_name(name):
    name = name.replace("Manchester", "Man.")
    name = name.replace("FC ", "").replace(" FC", "")
    return name.strip()


def to_local(utc_date_str):
    dt_utc = datetime.strptime(utc_date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return dt_utc.astimezone(LOCAL_TZ)


# --- Primary source: official .ics calendar feed ---

def parse_ics_summary(summary):
    """'{Home} vs {Away} - {Competition}' -> (home, away, competition)."""
    teams_part, _, competition = summary.rpartition(" - ")
    home, _, away = teams_part.partition(" vs ")
    return home.strip(), away.strip(), competition.strip()


def fetch_ics_matches(date_from, date_to):
    """
    Returns match dicts in the SAME shape fetch_football_data_matches() produces,
    so the rest of the pipeline doesn't need to know which source was used.
    """
    resp = requests.get(ICS_URL, headers=ICS_HEADERS, timeout=30)
    resp.raise_for_status()

    cal = Calendar.from_ical(resp.content)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    if not events:
        raise ValueError("ICS feed returned zero events — treating as a failure")

    date_from_d = date.fromisoformat(date_from)
    date_to_d = date.fromisoformat(date_to)

    matches = []
    for e in events:
        summary = str(e.get("summary", ""))
        dtstart = e.get("dtstart")
        if not dtstart:
            continue
        dt_utc = dtstart.dt  # already timezone-aware (UTC) per the feed
        local_dt = dt_utc.astimezone(LOCAL_TZ)

        if not (date_from_d <= local_dt.date() <= date_to_d):
            continue

        home, away, competition = parse_ics_summary(summary)
        if not home or not away:
            continue

        matches.append({
            "utcDate": dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "homeTeam": {"name": home},
            "awayTeam": {"name": away},
            "competition": {"name": competition},
            "status": "SCHEDULED",
        })

    return matches


# --- Fallback source: football-data.org ---

def fetch_football_data_matches(date_from, date_to):
    url = f"https://api.football-data.org/v4/teams/{TEAM_ID}/matches"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    params = {"dateFrom": date_from, "dateTo": date_to}

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    matches = data.get("matches", [])
    return [m for m in matches if m.get("status") not in EXCLUDED_STATUSES]


def fetch_fixtures(date_from, date_to):
    """Try the official .ics feed first; fall back to football-data.org on any failure."""
    try:
        matches = fetch_ics_matches(date_from, date_to)
        print(f"Fetched {len(matches)} matches from the official .ics feed.")
        return matches
    except Exception as e:
        print(f"WARNING: .ics fetch failed ({e}) — falling back to football-data.org.")
        matches = fetch_football_data_matches(date_from, date_to)
        print(f"Fetched {len(matches)} matches from football-data.org (fallback).")
        return matches


def to_frontend_fixture(m):
    local_dt = to_local(m["utcDate"])
    return {
        "day_label": local_dt.strftime("%a %-d %b"),
        "time_label": local_dt.strftime("%H:%M"),
        "home": shorten_name(m["homeTeam"]["name"]),
        "away": shorten_name(m["awayTeam"]["name"]),
        "competition": m.get("competition", {}).get("name", ""),
        "status": m.get("status"),
        "month": local_dt.month,
        "year": local_dt.year,
    }


def main():
    date_from, date_to = get_date_range()
    print(f"Fetching fixtures from {date_from} to {date_to}")

    matches = fetch_fixtures(date_from, date_to)
    matches.sort(key=lambda m: m["utcDate"])  # full ISO datetime — correct chronological order
    fixtures = [to_frontend_fixture(m) for m in matches]

    today = date.today()
    if today.month == 12:
        next_year, next_month_num = today.year + 1, 1
    else:
        next_year, next_month_num = today.year, today.month + 1

    this_month = [f for f in fixtures if f["year"] == today.year and f["month"] == today.month]
    next_month = [f for f in fixtures if f["year"] == next_year and f["month"] == next_month_num]

    output = {
        "this_month_label": f"{calendar.month_name[today.month]} {today.year}",
        "next_month_label": f"{calendar.month_name[next_month_num]} {next_year}",
        "this_month": this_month,
        "next_month": next_month,
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Saved {len(this_month)} this-month + {len(next_month)} next-month fixtures to {OUTPUT_FILE}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
