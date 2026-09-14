import sys
import requests
from icalendar import Calendar

ICS_URL = "https://www.manutd.com/en/Manchester_United.ics"

# Calendar client apps (Google/Outlook/Apple) don't identify as bots when they
# poll this feed — using a normal browser-like User-Agent here for the same reason.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

CUP_KEYWORDS = ["fa cup", "carabao", "league cup", "community shield", "efl cup"]


def main():
    print(f"Fetching: {ICS_URL}")
    resp = requests.get(ICS_URL, headers=HEADERS, timeout=30)
    print(f"HTTP status: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('Content-Type')}")
    print(f"Response length: {len(resp.content)} bytes")

    resp.raise_for_status()

    cal = Calendar.from_ical(resp.content)
    events = [c for c in cal.walk() if c.name == "VEVENT"]
    print(f"\nTotal events found: {len(events)}")

    cup_matches_found = []

    print("\n--- All events (raw fields) ---")
    for e in events:
        summary = str(e.get("summary", ""))
        dtstart = e.get("dtstart")
        dtstart_str = dtstart.dt.isoformat() if dtstart else "?"
        description = str(e.get("description", ""))
        location = str(e.get("location", ""))
        categories = str(e.get("categories", ""))

        print(f"\nSUMMARY:     {summary}")
        print(f"DTSTART:     {dtstart_str}")
        print(f"LOCATION:    {location}")
        print(f"CATEGORIES:  {categories}")
        if description:
            print(f"DESCRIPTION: {description[:200]}")

        combined_text = f"{summary} {description} {categories}".lower()
        if any(kw in combined_text for kw in CUP_KEYWORDS):
            cup_matches_found.append(summary)

    print(f"\n--- Cup-competition keyword matches ---")
    if cup_matches_found:
        for m in cup_matches_found:
            print(f"  FOUND: {m}")
    else:
        print("  None found — competition info may not be in these fields, or no cup fixtures scheduled right now.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
