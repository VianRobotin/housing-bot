import json
import os
import re
import xml.etree.ElementTree as ET
from urllib.parse import quote

import requests

SITEMAP_URL = "https://roofz.eu/__sitemap__/properties-0.xml"
SEEN_FILE = "seen_properties.json"
PROPERTY_BASE = "https://roofz.eu/huur/woningen/"

WHATSAPP_PHONE = os.environ["WHATSAPP_PHONE"]
CALLMEBOT_APIKEY = os.environ["CALLMEBOT_APIKEY"]

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def fetch_sitemap_urls():
    resp = requests.get(SITEMAP_URL, timeout=30, headers=HEADERS)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [el.find("sm:loc", ns).text for el in root.findall("sm:url", ns)]
    # Only detail pages (not the index /huur/woningen)
    return [u for u in urls if u.startswith(PROPERTY_BASE) and len(u) > len(PROPERTY_BASE)]


def get_amsterdam_info(url):
    """Fetch property page. Returns (price, address) if Amsterdam, else None."""
    try:
        resp = requests.get(url, timeout=30, headers=HEADERS)
        text = resp.text

        # City check — match the structured city field, not just any occurrence
        if not re.search(r'"(?:city|addressLocality)"\s*:\s*"Amsterdam"', text):
            return None

        # Extract total rent
        price_match = re.search(r'"totalRent"\s*:\s*(\d+)', text)
        price = f"€{price_match.group(1)}/mo" if price_match else "price unknown"

        # Extract address from URL slug
        slug = url.rstrip("/").split("/")[-1]
        address = slug.replace("-", " ").title()

        return price, address
    except Exception as e:
        print(f"  Warning: failed to fetch {url}: {e}")
        return None


def send_whatsapp(message):
    encoded = quote(message)
    api_url = (
        f"https://api.callmebot.com/whatsapp.php"
        f"?phone={WHATSAPP_PHONE}&text={encoded}&apikey={CALLMEBOT_APIKEY}"
    )
    try:
        resp = requests.get(api_url, timeout=30)
        print(f"  WhatsApp sent (status {resp.status_code})")
    except Exception as e:
        print(f"  WhatsApp failed: {e}")


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def main():
    seen = load_seen()
    print(f"Loaded {len(seen)} previously seen properties")

    current_urls = set(fetch_sitemap_urls())
    print(f"Sitemap has {len(current_urls)} properties")

    # First run: just snapshot current state, no notifications
    if not seen:
        save_seen(current_urls)
        print(f"First run: snapshotted {len(current_urls)} existing properties. Will notify on new ones next run.")
        return

    new_urls = current_urls - seen
    print(f"Found {len(new_urls)} new URL(s) to check")

    notified = 0
    for url in sorted(new_urls):
        print(f"  Checking: {url}")
        result = get_amsterdam_info(url)
        if result:
            price, address = result
            message = f"New Amsterdam listing on Roofz!\n{address} - {price}\n{url}"
            print(f"  Amsterdam match! Notifying: {address} {price}")
            send_whatsapp(message)
            notified += 1

    print(f"Notified for {notified} new Amsterdam listing(s)")

    # Persist all seen URLs (existing + new, regardless of city)
    save_seen(seen | current_urls)


if __name__ == "__main__":
    main()
