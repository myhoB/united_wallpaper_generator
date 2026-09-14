import os
import sys
import requests

API_KEY = os.environ["API_FOOTBALL"]
TEAM_ID = 33  # Manchester United, confirmed via API-Football's own docs
SEASON = 2026  # season is identified by its starting year

# Note: if you signed up directly at api-football.com, auth uses this header.
# If you went through RapidAPI instead, it needs x-rapidapi-key + x-rapidapi-host
# instead — let me know if this gets a 401/403 and we'll swap it.
HEADERS = {"x-apisports-key": API_KEY}
BASE_URL = "https://v3.football.api-sports.io"


def fetch_fixtures():
    url = f"{BASE_URL}/fixtures"
    params = {"team": TEAM_ID, "season": SEASON}
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main():
    print(f"Fetching all fixtures for team {TEAM_ID}, season {SEASON}...")
    data = fetch_fixtures()

    errors = data.get("errors")
    if errors:
        print(f"API returned errors: {errors}", file=sys.stderr)

    fixtures = data.get("response", [])
    print(f"Total fixtures returned: {len(fixtures)}")
    print(f"Results count field: {data.get('results')}")

    competitions = {}
    for fx in fixtures:
        league_name = fx.get("league", {}).get("name", "Unknown")
        competitions[league_name] = competitions.get(league_name, 0) + 1

    print("\n--- Competitions found ---")
    for name, count in sorted(competitions.items()):
        print(f"  {name}: {count} fixture(s)")

    print("\n--- Sample fixtures ---")
    for fx in fixtures[:15]:
        date = fx.get("fixture", {}).get("date", "?")
        league = fx.get("league", {}).get("name", "?")
        home = fx.get("teams", {}).get("home", {}).get("name", "?")
        away = fx.get("teams", {}).get("away", {}).get("name", "?")
        print(f"  {date} | {league} | {home} vs {away}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
