import os
import sys
import json
import requests

SERP_API_KEY = os.environ["SERP_API"]
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")  # optional — notification is skipped if not set
CONFIG_FILE = "image_search_config.json"
OUTPUT_FILE = "docs/candidates.json"
MAX_CANDIDATES = 12
NEW_CANDIDATE_ALERT_THRESHOLD = 6


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def is_excluded(result, excluded_domains):
    source = (result.get("source") or "").lower()
    link = (result.get("link") or "").lower()
    original = (result.get("original") or "").lower()
    return any(domain in source or domain in link or domain in original for domain in excluded_domains)


def is_portrait(result):
    width = result.get("original_width") or 0
    height = result.get("original_height") or 0
    return height > width


def search_images(query, excluded_domains, num_results=20):
    """Query SerpApi's Google Images engine for candidate photos."""
    params = {
        "engine": "google_images",
        "q": query,
        "api_key": SERP_API_KEY,
        "tbs": "qdr:m,isz:l",
        "num": num_results,
    }
    resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("images_results", [])

    results = [r for r in results if not is_excluded(r, excluded_domains)]
    results = [r for r in results if not is_portrait(r)]
    return results


def sort_candidates(results):
    return sorted(
        results,
        key=lambda r: (r.get("original_width") or 0) * (r.get("original_height") or 0),
        reverse=True,
    )


def to_frontend_format(results):
    """Trim each result down to just what the picker page needs."""
    trimmed = []
    for r in results[:MAX_CANDIDATES]:
        trimmed.append({
            "image_url": r.get("original"),
            "thumbnail_url": r.get("thumbnail"),
            "width": r.get("original_width"),
            "height": r.get("original_height"),
            "source": r.get("source"),
            "title": r.get("title"),
        })
    return trimmed


def load_previous_candidates():
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def count_new_candidates(new_candidates, previous_candidates):
    previous_urls = {c.get("image_url") for c in previous_candidates}
    return sum(1 for c in new_candidates if c.get("image_url") not in previous_urls)


def send_ntfy_alert(new_count):
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set — skipping notification.")
        return
    url = f"https://ntfy.sh/{NTFY_TOPIC}"
    headers = {
        "Title": "New wallpapers were found".encode("utf-8"),
        "Priority": "default",
        "Tags": "camera",
    }
    message = f"{new_count} new candidate photo{'s' if new_count != 1 else ''} found for the wallpaper picker."
    resp = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=30)
    resp.raise_for_status()
    print("Sent ntfy notification.")


def main():
    config = load_config()
    query = config["search_query"]
    excluded_domains = config.get("excluded_domains", [])

    print(f"Searching: {query}")
    results = search_images(query, excluded_domains)
    results = sort_candidates(results)
    print(f"Found {len(results)} usable candidates, keeping top {MAX_CANDIDATES}")

    frontend_data = to_frontend_format(results)

    previous_candidates = load_previous_candidates()
    new_count = count_new_candidates(frontend_data, previous_candidates)
    print(f"{new_count} of these are new compared to the previous candidates.json")

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(frontend_data, f, indent=2)

    print(f"Saved {len(frontend_data)} candidates to {OUTPUT_FILE}")

    if new_count >= NEW_CANDIDATE_ALERT_THRESHOLD:
        send_ntfy_alert(new_count)
    else:
        print(f"Below alert threshold ({NEW_CANDIDATE_ALERT_THRESHOLD}) — no notification sent.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
