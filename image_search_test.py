import os
import sys
import requests

SERP_API_KEY = os.environ["SERP_API"]

EXCLUDED_DOMAINS = {"instagram.com"}


def is_excluded(result):
    source = (result.get("source") or "").lower()
    link = (result.get("link") or "").lower()
    original = (result.get("original") or "").lower()
    return any(domain in source or domain in link or domain in original for domain in EXCLUDED_DOMAINS)


def search_images(query, num_results=10):
    """Query SerpApi's Google Images engine for candidate photos."""
    params = {
        "engine": "google_images",
        "q": query,
        "api_key": SERP_API_KEY,
        # tbs filters: qdr:m = past month, isz:l = large images only
        "tbs": "qdr:m,isz:l",
        "num": num_results,
    }
    resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    results = data.get("images_results", [])

    return [r for r in results if not is_excluded(r)]


def print_candidates(results):
    if not results:
        print("No results returned.")
        return

    for i, r in enumerate(results, 1):
        print(f"\n--- Candidate {i} ---")
        print(f"Title:      {r.get('title')}")
        print(f"Source:     {r.get('source')}")
        print(f"Image URL:  {r.get('original')}")
        print(f"Dimensions: {r.get('original_width')}x{r.get('original_height')}")
        print(f"Page link:  {r.get('link')}")


def main():
    # Simple test query — we'll make this dynamic per-fixture later
    query = "Manchester United match action photo"
    print(f"Searching: {query}\n")

    results = search_images(query)
    print(f"Found {len(results)} candidates")
    print_candidates(results)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
