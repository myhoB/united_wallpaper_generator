import os
import sys
import json
import requests

SERP_API_KEY = os.environ["SERP_API"]
CONFIG_FILE = "image_search_config.json"


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def is_excluded(result, excluded_domains):
    source = (result.get("source") or "").lower()
    link = (result.get("link") or "").lower()
    original = (result.get("original") or "").lower()
    return any(domain in source or domain in link or domain in original for domain in excluded_domains)


def search_images(query, excluded_domains, num_results=10):
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

    return [r for r in results if not is_excluded(r, excluded_domains)]


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
    config = load_config()
    query = config["search_query"]
    excluded_domains = config.get("excluded_domains", [])

    print(f"Searching: {query}")
    print(f"Excluding domains: {excluded_domains}\n")

    results = search_images(query, excluded_domains)
    print(f"Found {len(results)} candidates")
    print_candidates(results)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
