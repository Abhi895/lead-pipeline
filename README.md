# Local lead pipeline

Two scripts: one finds businesses with no website (or a clearly neglected
one) and writes them to a CSV; the other generates a ready-to-show HTML
mockup for each one. The actual call/WhatsApp/close stays manual on purpose
- that's the part that actually converts, and it's the part only you can do.

## 1. Setup

```bash
pip install requests anthropic
export GOOGLE_PLACES_API_KEY="your-key-here"
export ANTHROPIC_API_KEY="your-key-here"
```

Get a Google Places API key from the Google Cloud Console (enable "Places
API (New)"). Check current pricing for Text Search before running this at
volume - it bills per request, and cost scales with how many businesses you
search for.

For Anthropic API pricing, check the current rates on the API console -
`generate_mockups.py` defaults to `claude-sonnet-4-6`; swap to
`claude-haiku-4-5-20251001` in the `--model` flag if you want a cheaper pass
for a first draft on lots of leads, then re-run the good ones on Sonnet.

## 2. Find leads

```bash
python find_leads.py "plumbers in Motherwell" --max 20 --out plumbers.csv
```

This searches Google Places, checks each business's listed website (if any)
for staleness signals (no mobile viewport tag, old Joomla-style URLs,
copyright years more than 5 years old), and writes everything to a CSV with
a `flag` column: `no_website`, `stale`, `ok`, or `unreachable`.

Open the CSV and skim it - the heuristics are a starting filter, not a
verdict. Spot-check a few of the `stale` ones yourself before trusting the
flag.

## 3. Generate mockups

```bash
python generate_mockups.py --leads plumbers.csv --category "plumber" --out-dir mockups/plumbers
```

For every lead flagged `no_website` or `stale`, this calls the Claude API
and writes a single-file HTML homepage to the output folder, named after
the business. Open each one in a browser before sending anything - some
will need a tweak (wrong phone format, generic copy that needs a personal
line added, etc.).

## 4. The part that isn't automated, deliberately

Call or WhatsApp the business with something like:

> "Hi, I'm a local web developer - I noticed [business] doesn't have a
> website / your current site looks a bit dated, so I went ahead and built
> you a free mockup of what one could look like: [link]. If you like it, I
> can have it live for £500."

This is the step that actually converts. A mass-emailed link reads as spam
and converts far worse than the same link delivered in a real conversation
- automating this step would cost you more in trust than it saves in time.

## Notes

- `find_leads.py` adds a 1 second delay between site checks - don't remove
  this, it's there to avoid hammering small business servers.
- Re-running `generate_mockups.py` skips businesses that already have a
  mockup file, so it's safe to re-run after adding new leads to a CSV.
- These are mockups, not final builds - don't hand over the generated HTML
  as the finished product. Treat it as the pitch asset, then build the real
  site properly once someone says yes.
