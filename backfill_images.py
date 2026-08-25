"""
backfill_images.py
-------------------
One-time / resumable maintenance script that fetches real product photos
from the KicksDB API (StockX Standard API) and writes them into
data/sneakerdata.json as an `image` field per sneaker.

Why this exists: sneakerdata.json ships with no photo URLs — the catalog
UI previously rendered a flat colorway-derived color block instead of a
real image. This script backfills real photos once, offline; the running
app never calls KicksDB at request time, it just reads the `image` field
already saved on each catalog entry.

KicksDB's free tier caps requests at 1,000/month, and the catalog has
1,668 sneakers, so this script is deliberately resumable:
  - Sneakers are prioritized by sales_this_period (most-viewed first).
  - A sneaker that already has an `image` is skipped.
  - A sneaker with no match on KicksDB is marked `image_lookup_failed`
    so future runs don't spend quota re-querying a name that will never
    match, instead of leaving it stuck in an endless "still missing" state.
  - The run stops at MAX_REQUESTS_PER_RUN so a single run never exceeds
    the free-tier monthly cap. Run again next billing cycle (or after
    upgrading the plan) to continue backfilling the remainder.

Setup:
  1. Create a free account at https://kicks.dev and generate an API key.
  2. Add KICKS_API_KEY=<your key> to .env (never commit this file).
  3. Run: python backfill_images.py

Cost: free tier, 1,000 requests/month — no cost as long as usage stays
under that cap. See README for the tier tradeoff.
"""

import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv(override=True)

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "data", "sneakerdata.json")
API_BASE = "https://api.kicks.dev/v3/stockx/products"
MAX_REQUESTS_PER_RUN = 1000       # stays within the free-tier monthly cap
REQUEST_DELAY_SECONDS = 0.3       # polite pacing between calls
SAVE_EVERY = 25                   # persist progress periodically, not just at the end


def load_catalog():
    """
    load_catalog
    ------------
    Reads the full sneaker catalog JSON file from disk.

    Args:
        None

    Returns:
        dict: catalog keyed by sneaker name
    """
    with open(CATALOG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_catalog(catalog):
    """
    save_catalog
    ------------
    Writes the catalog back to disk, preserving readable formatting.

    Args:
        catalog (dict): full catalog, including any newly added image fields

    Returns:
        None
    """
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)


def fetch_image_url(name, api_key):
    """
    fetch_image_url
    ----------------
    Searches KicksDB's StockX Standard API for a sneaker by name and
    returns the first result's image URL.

    Distinguishes a genuine "no match" (a clean 200 response with no
    results — this sneaker isn't in StockX's catalog under this name,
    and never will be) from a transient failure (network error, 5xx
    server error, malformed response — may well succeed if retried).
    Only the former should be treated as permanent, so main() knows
    whether it's safe to stop retrying this name on future runs.

    Args:
        name    (str): sneaker name as it appears in the catalog
        api_key (str): KicksDB API key

    Returns:
        tuple[str | None, bool]: (image_url, is_permanent_failure).
          - (url, False)  — found a match
          - (None, True)  — genuine no-match, safe to stop retrying
          - (None, False) — transient failure, should be retried later
    """
    try:
        response = requests.get(
            API_BASE,
            params={"query": name},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
    except requests.RequestException as exc:
        print(f"  ! network error for '{name}' (will retry later): {exc}")
        return None, False

    if response.status_code != 200:
        print(f"  ! HTTP {response.status_code} for '{name}' (will retry later)")
        return None, False

    try:
        body = response.json()
    except ValueError:
        print(f"  ! malformed response for '{name}' (will retry later)")
        return None, False

    data = body.get("data")

    if isinstance(data, list):
        data = data[0] if data else None

    if not data:
        return None, True

    return _upsize_image_url(data.get("image")), False


def _upsize_image_url(image_url):
    """
    _upsize_image_url
    ------------------
    KicksDB's default search result image is a small w=140&h=100 thumbnail.
    The StockX image CDN accepts the same w/h query params at any size, so
    this swaps in a display-appropriate resolution for the catalog card.

    Args:
        image_url (str | None): the raw image URL from the API response

    Returns:
        str | None: the same URL with larger w/h params, or the original
                     value unchanged if it doesn't match the expected
                     thumbnail pattern
    """
    if not image_url:
        return image_url

    return image_url.replace("w=140", "w=640").replace("h=100", "h=460")


def main():
    """
    main
    ----
    Backfills images for the highest-priority sneakers that still need
    one, saving progress periodically so an interruption never loses
    work, and prints a summary of what remains for the next run.

    Args:
        None

    Returns:
        None
    """
    api_key = os.environ.get("KICKS_API_KEY")
    if not api_key:
        print("KICKS_API_KEY is not set. Add it to .env and try again.")
        return

    catalog = load_catalog()

    missing = [
        name for name, details in catalog.items()
        if not details.get("image") and not details.get("image_lookup_failed")
    ]
    missing.sort(
        key=lambda name: catalog[name].get("sales_this_period", 0),
        reverse=True,
    )

    batch = missing[:MAX_REQUESTS_PER_RUN]
    print(f"{len(missing)} sneakers still need an image lookup.")
    print(f"Fetching the top {len(batch)} by popularity this run "
          f"(free-tier cap: {MAX_REQUESTS_PER_RUN}/month).")

    fetched   = 0
    no_match  = 0
    retryable = 0

    for i, name in enumerate(batch, start=1):
        image_url, is_permanent_failure = fetch_image_url(name, api_key)

        if image_url:
            catalog[name]["image"] = image_url
            fetched += 1
        elif is_permanent_failure:
            catalog[name]["image_lookup_failed"] = True
            no_match += 1
        else:
            # Transient error — leave unmarked so it's retried next run.
            retryable += 1

        if i % SAVE_EVERY == 0:
            save_catalog(catalog)
            print(f"  [{i}/{len(batch)}] progress saved "
                  f"({fetched} found, {no_match} no match, {retryable} to retry)")

        time.sleep(REQUEST_DELAY_SECONDS)

    save_catalog(catalog)

    remaining = len(missing) - fetched - no_match
    print()
    print(f"Done. {fetched} images added, {no_match} had no match, "
          f"{retryable} hit a transient error and will be retried automatically.")
    if remaining > 0:
        print(f"{remaining} sneakers still need a lookup — "
              f"run this script again next billing cycle to continue.")


if __name__ == "__main__":
    main()
