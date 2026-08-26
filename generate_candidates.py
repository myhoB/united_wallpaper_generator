import os
import sys
import json
import requests

SERP_API_KEY = os.environ["SERP_API"]
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")  # optional — notification is skipped if not set
CONFIG_FILE = "image_search_config.json"
OUTPUT_FILE = "docs/candidates.json"
MAX_CANDIDATES = 40
NEW_CANDIDATE_ALERT_THRESHOLD = 15


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def is_excluded(result, excluded_domains):
    source = (result.get("source") or "").lower()
    link = (result.get("link") or "").lower()
    original = (result.get("original") or "").lower()
    return any(domain in source or domain in link or domain in original for domain in excluded_domains)


def is_landscape(result):
    """Keep only images wider than they are tall — the shape we actually want."""
    width = result.get("original_width") or 0
    height = result.get("original_height") or 0
    return width > height


def search_google_images(query, num_results=100):
    """
    Google Images via SerpApi.
    tbs breakdown:
      qdr:m            -> posted within the past month
      isz:lt,islt:2mp  -> larger than ~1600x1200 (explicit size floor, not the vague "large" bucket)
      itp:photo        -> photographs only — excludes clipart, line drawings, graphics
    """
    params = {
        "engine": "google_images",
        "q": query,
        "api_key": SERP_API_KEY,
        "tbs": "qdr:m,isz:lt,islt:2mp,itp:photo",
        "num": num_results,
    }
    resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json().get("images_results", [])


def search_bing_images(query, count=50):
    """
    Bing Images via SerpApi — same account/key, no separate signup needed.
    photo='photo'         -> photographs only, excludes graphics/clipart
    imagesize='wallpaper' -> Bing's own high-resolution bucket
    aspect='wide'         -> landscape orientation (belt-and-braces with our own is_landscape check)
    age='lt43200'         -> newer than 43200 minutes (~30 days)

    Wrapped defensively: if this engine or its params ever change/break, we fall
    back to Google-only results rather than failing the whole run.
    """
    params = {
        "engine": "bing_images",
        "q": query,
        "api_key": SERP_API_KEY,
        "count": count,
        "photo": "photo",
        "imagesize": "wallpaper",
        "aspect": "wide",
        "age": "lt43200",
    }
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
        resp.raise_for_status()
        raw_results = resp.json().get("images_results", [])
    except Exception as e:
        print(f"WARNING: Bing search failed, continuing with Google results only: {e}")
        return []

    # Normalize to the same shape as Google's results — Bing's field names
    # can differ slightly, so check a couple of likely alternatives defensively.
    normalized = []
    for r in raw_results:
        normalized.append({
            "original": r.get("original") or r.get("image") or r.get("link"),
            "original_width": r.get("original_width") or r.get("width"),
            "original_height": r.get("original_height") or r.get("height"),
            "thumbnail": r.get("thumbnail"),
            "source": r.get("source"),
            "link": r.get("link"),
            "title": r.get("title"),
        })
    return normalized


def dedupe_by_url(results):
    seen = set()
    deduped = []
    for r in results:
        url = r.get("original")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(r)
    return deduped


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

    print(f"Searching Google Images: {query}")
    google_results = search_google_images(query)
    print(f"  {len(google_results)} raw results")

    print(f"Searching Bing Images: {query}")
    bing_results = search_bing_images(query)
    print(f"  {len(bing_results)} raw results")

    combined = dedupe_by_url(google_results + bing_results)
    print(f"{len(combined)} combined results after de-duplication")

    results = [r for r in combined if not is_excluded(r, excluded_domains)]
    results = [r for r in results if is_landscape(r)]
    print(f"{len(results)} usable candidates after domain/orientation filtering, keeping top {MAX_CANDIDATES}")

    results = sort_candidates(results)
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
