# Emergency California — offline-first disaster response (v1, Stage 1 in progress)

> **⚠️ NOT MEDICAL ADVICE.** Every first-aid entry in this repo is
> `review_status: UNVETTED_DRAFT` — AI-assisted schema-filler content that has
> **not** been reviewed by a clinician and must be replaced before anything
> ships. Nothing here replaces professional care. **In an emergency, call 911.**
> Shelter locations are seed drafts from public listings; activation is
> incident-dependent — verify before relying on them.

## Architecture in one paragraph

Two zones separated by a sync boundary. The **backend** runs only during calm,
when networks work: it builds a versioned content bundle (one SQLite file with
first-aid entries, shelters, an FTS5 search index, plus a manifest) from open
sources. The **device** holds a cached copy of that bundle and, during the
emergency, reads *only* from it — no network call may sit on any
emergency-time path. A user opens the app with towers down and still gets
searchable vetted first-aid guidance, nearby shelter and evacuation points,
and (in later stages) an offline map with a live GPS blue dot.

## Layout

- `backend/` — calm-time zone: `schema.sql`, `build_bundle.py`, draft content
- `sync/` — the boundary contract (thin API in a later stage)
- `bundle/` — build output (gitignored): `bundle.db` + `manifest.json`
- `device/` — emergency-time zone: `query.py` (zero-network retrieval + CLI)
- `evals/` — Track B groundedness harness (dev-time only, never on device)
- `pwa/` — Stage 1 React emergency surface. It opens the unchanged SQLite
  bundle with an FTS5-enabled browser SQLite runtime, runs the same retrieval
  cascade, and caches app-owned assets locally with a service worker.

## Quickstart

```bash
python backend/build_bundle.py                 # content/ -> bundle/
python device/query.py "cant stop the bleeding"
python device/query.py --near 37.87,-122.27    # nearest shelters
python device/tests/test_offline.py            # full path with sockets blocked
python evals/run_evals.py                      # Track B (needs ANTHROPIC_API_KEY)
cd pwa && npm run test:parity && npm run build # browser retrieval + PWA build
```

`device/` uses only the Python standard library. `requirements.txt` exists
solely for the eval harness. Copy `.env.example` to `.env` for eval runs.

The PWA uses only its packaged `bundle/bundle.db`, manifest, browser GPS, and
app-owned cached files on its emergency-time path. `pwa/public/bundle/` does
not yet contain a reviewed Bay Area PMTiles map pack, so the current map shows
local shelter points and GPS over a neutral background until that input lands.

## Why the eval harness exists

The device never generates first-aid text with an LLM — it retrieves vetted
entries. `evals/` proves that design choice: it compares retrieval-grounded
answering against a free LLM on a gold set of panicked, terse, and
out-of-scope queries, and measures how often each configuration says things
not present in the vetted content (the ungrounded rate). Grounded-and-safe is
the product's core claim; the harness is its evidence.
