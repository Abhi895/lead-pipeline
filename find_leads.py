"""
find_leads.py — find local businesses with no or stale websites.

Usage:
    python find_leads.py "plumbers in Motherwell" --max 20 --out plumbers.csv

Requires:
    pip install requests
    export GOOGLE_PLACES_API_KEY="your-key"
"""

import argparse
import csv
import os
import re
import time

import requests

PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY")
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = (
    "places.displayName,"
    "places.formattedAddress,"
    "places.websiteUri,"
    "places.nationalPhoneNumber,"
    "places.rating,"
    "places.userRatingCount,"
    "nextPageToken"
)

# A copyright year this old or older counts as stale (2026 - 5 = 2021)
STALE_YEAR_THRESHOLD = 2021

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

OLD_CMS_PATTERNS = [
    r"index\.php\?option=com_",   # Joomla
    r"itemid=\d+",                # Joomla
    r"/administrator/",           # Joomla admin leak
    r"wp-content/themes/twentyten",
    r"wp-content/themes/twentyeleven",
    r"wp-content/themes/twentytwelve",
    r"wp-content/themes/twentythirteen",
]

OLD_DOCTYPE = re.compile(
    r'<!DOCTYPE\s+HTML\s+PUBLIC\s+["\'].*?//DTD\s+HTML\s+4',
    re.IGNORECASE,
)

COPYRIGHT_RE = re.compile(
    r"(?:©|&copy;|copyright|\(c\))[^<]{0,40}?((?:19|20)\d{2})",
    re.IGNORECASE,
)


def search_places(query: str, max_results: int) -> list[dict]:
    results = []
    page_token = None

    while len(results) < max_results:
        body: dict = {
            "textQuery": query,
            "pageSize": min(20, max_results - len(results)),
        }
        if page_token:
            body["pageToken"] = page_token

        resp = requests.post(
            PLACES_URL,
            json=body,
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": PLACES_API_KEY,
                "X-Goog-FieldMask": FIELD_MASK,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        places = data.get("places", [])
        if not places:
            break

        results.extend(places)
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return results[:max_results]


def check_website(url: str) -> tuple[str, list[str]]:
    """
    Returns (flag, reasons).
    flag is one of: 'ok', 'stale', 'unreachable'
    """
    try:
        resp = requests.get(
            url,
            timeout=10,
            headers=HEADERS,
            allow_redirects=True,
            verify=False,   # many small biz sites have expired certs
        )
        html = resp.text
        html_lower = html.lower()
        reasons = []

        # 1. No mobile viewport
        if 'name="viewport"' not in html_lower and "name='viewport'" not in html_lower:
            reasons.append("no_viewport")

        # 2. Old/no HTTPS
        if resp.url.startswith("http://"):
            reasons.append("no_https")

        # 3. HTML4 doctype
        if OLD_DOCTYPE.search(html):
            reasons.append("html4_doctype")

        # 4. Flash
        if "application/x-shockwave-flash" in html_lower or ".swf" in html_lower:
            reasons.append("flash")

        # 5. Old CMS fingerprints
        for pattern in OLD_CMS_PATTERNS:
            if re.search(pattern, html_lower):
                reasons.append("old_cms")
                break

        # 6. Stale copyright year
        years = [int(m) for m in COPYRIGHT_RE.findall(html)]
        if years:
            latest = max(years)
            if latest <= STALE_YEAR_THRESHOLD:
                reasons.append(f"copyright_{latest}")

        flag = "stale" if reasons else "ok"
        return flag, reasons

    except requests.exceptions.SSLError:
        # Try without SSL verification already set, so this means total failure
        return "unreachable", ["ssl_error"]
    except requests.exceptions.Timeout:
        return "unreachable", ["timeout"]
    except requests.exceptions.ConnectionError:
        return "unreachable", ["connection_error"]
    except Exception as e:
        return "unreachable", [str(e)[:60]]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find local businesses with no or stale websites."
    )
    parser.add_argument("query", help='e.g. "plumbers in Motherwell"')
    parser.add_argument("--max", type=int, default=20, help="Max businesses to check")
    parser.add_argument("--out", required=True, help="Output CSV path")
    args = parser.parse_args()

    if not PLACES_API_KEY:
        raise SystemExit("Error: GOOGLE_PLACES_API_KEY environment variable not set.")

    # Suppress the SSL warning we're intentionally ignoring
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    print(f"Searching: {args.query!r}")
    places = search_places(args.query, args.max)
    print(f"Found {len(places)} businesses\n")

    rows = []
    for i, place in enumerate(places, 1):
        name = place.get("displayName", {}).get("text", "")
        address = place.get("formattedAddress", "")
        phone = place.get("nationalPhoneNumber", "")
        website = place.get("websiteUri", "")
        rating = place.get("rating", "")
        review_count = place.get("userRatingCount", "")

        label = f"[{i}/{len(places)}] {name}"

        if not website:
            flag, reasons = "no_website", []
            print(f"{label} → no_website")
        else:
            flag, reasons = check_website(website)
            reason_str = f" ({', '.join(reasons)})" if reasons else ""
            print(f"{label} → {flag}{reason_str}")
            time.sleep(1)

        rows.append({
            "name": name,
            "address": address,
            "phone": phone,
            "website": website,
            "rating": rating,
            "review_count": review_count,
            "flag": flag,
            "stale_reasons": ", ".join(reasons),
        })

    fieldnames = ["name", "address", "phone", "website", "rating", "review_count", "flag", "stale_reasons"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total_leads = sum(1 for r in rows if r["flag"] in ("no_website", "stale"))
    print(f"\nWrote {len(rows)} rows → {args.out}")
    print(f"Actionable leads (no_website + stale): {total_leads}")


if __name__ == "__main__":
    main()
