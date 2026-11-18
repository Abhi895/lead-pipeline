"""
generate_mockups.py — generate HTML website mockups for leads using Claude.

Usage:
    python generate_mockups.py --leads plumbers.csv --category "plumber" --out-dir mockups/plumbers

Skips businesses that already have a mockup file, so safe to re-run.

Requires:
    pip install anthropic
    export ANTHROPIC_API_KEY="your-key"
"""

import argparse
import csv
import os
import re

import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")


def sanitize_filename(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    name = re.sub(r"\s+", "-", name.strip())
    name = re.sub(r"-+", "-", name)
    return name[:80]


def build_prompt(name: str, address: str, phone: str, category: str,
                 rating: str, review_count: str, existing_website: str) -> str:

    lines = [
        f"Business name: {name}",
        f"Category: {category}",
        f"Address: {address}",
    ]
    if phone:
        lines.append(f"Phone: {phone}")
    if rating:
        lines.append(f"Google rating: {rating}/5 ({review_count} reviews)")
    if existing_website:
        lines.append(f"Existing website (outdated): {existing_website}")
    else:
        lines.append("No existing website.")

    details = "\n".join(lines)

    return f"""Build a single-file HTML website mockup for a local {category} business to use as a sales pitch. It must look professional and complete when opened in a browser.

Business details:
{details}

STRICT RULES — follow these exactly:
- Output ONLY raw HTML starting with <!DOCTYPE html>. No explanation, no markdown fences.
- Single file: all CSS in one <style> tag, no external CSS files. Google Fonts @import is fine.
- Keep CSS simple and concise — no complex animations, no backdrop-filter, no CSS custom property overload. Use plain colour values.
- Valid HTML5 with charset and viewport meta tags.
- Every phone number must be a tel: link.

DESIGN
- Clean, modern, trustworthy — appropriate for a local {category} in Scotland
- Colour scheme: plumber → navy/white, electrician → charcoal/yellow, roofer → slate/orange, decorator → white/green, driving instructor → navy/orange
- Readable typography, good spacing, subtle box-shadows — looks like a real local business site, not a SaaS product

SECTIONS (in order)
1. Nav — logo (business name), links (Services, About, Contact), prominent phone number
2. Hero — strong headline mentioning the local area, one-line subheading, two buttons: "Call Now" (tel: link) and "Get a Free Quote" (anchor to contact)
3. Services — 6 specific services for a {category} (e.g. "Boiler installation & replacement", not just "Boilers")
4. Why Us — 4 trust signals (local, certified if applicable, free quotes, fully insured)
5. Reviews — 3 five-star reviews with Scottish first names (Ewan, Fiona, Craig, Morag, Kieran, Isla) and specific realistic details
6. Contact — large phone as tel: link, address, simple non-functional contact form (name, phone, message)
7. Footer — business name, tagline, phone, address, © 2026

CONTENT
- Use the actual business name and local area throughout — no generic placeholders
- If a Google rating is provided, show it in a small banner below the nav{"" if not rating else f": Rated {rating}/5 on Google"}
- Write real copy — no lorem ipsum, no [placeholder] text"""


def generate_mockup(client: anthropic.Anthropic, lead: dict, category: str, model: str) -> str:
    prompt = build_prompt(
        name=lead["name"],
        address=lead["address"],
        phone=lead.get("phone", ""),
        category=category,
        rating=lead.get("rating", ""),
        review_count=lead.get("review_count", ""),
        existing_website=lead.get("website", ""),
    )

    message = client.messages.create(
        model=model,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    html = message.content[0].text.strip()

    # Strip accidental markdown fences
    if html.startswith("```"):
        html = re.sub(r"^```[^\n]*\n", "", html)
        html = re.sub(r"\n?```$", "", html.strip())

    return html


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate HTML mockups for leads using Claude."
    )
    parser.add_argument("--leads", required=True, help="CSV from find_leads.py")
    parser.add_argument("--category", required=True, help='e.g. "plumber"')
    parser.add_argument("--out-dir", required=True, help="Output directory for HTML files")
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Claude model (use claude-haiku-4-5-20251001 for cheaper first drafts)",
    )
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        raise SystemExit("Error: ANTHROPIC_API_KEY environment variable not set.")

    os.makedirs(args.out_dir, exist_ok=True)
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    with open(args.leads, newline="", encoding="utf-8") as f:
        leads = list(csv.DictReader(f))

    actionable = [r for r in leads if r["flag"] in ("no_website", "stale")]
    print(f"{len(actionable)} actionable leads in {args.leads}\n")

    generated = 0
    skipped = 0
    errors = 0

    for i, lead in enumerate(actionable, 1):
        name = lead["name"]
        slug = sanitize_filename(name)
        out_path = os.path.join(args.out_dir, f"{slug}.html")

        if os.path.exists(out_path):
            print(f"[{i}/{len(actionable)}] {name} — already exists, skipping")
            skipped += 1
            continue

        print(f"[{i}/{len(actionable)}] {name} — generating...", end=" ", flush=True)

        try:
            html = generate_mockup(client, lead, args.category, args.model)

            with open(out_path, "w", encoding="utf-8") as f:
                f.write(html)

            print(f"done → {out_path}")
            generated += 1

        except Exception as e:
            print(f"ERROR: {e}")
            errors += 1

    print(f"\nGenerated: {generated}  |  Skipped: {skipped}  |  Errors: {errors}")
    if generated:
        print("Open each HTML file in a browser and review before using as a pitch asset.")


if __name__ == "__main__":
    main()
