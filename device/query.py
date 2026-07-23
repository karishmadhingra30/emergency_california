"""Emergency-time query path. OFFLINE ONLY — reads bundle/bundle.db, never the
network. This module is both the Stage 0 CLI and the retrieval library that the
eval harness imports, so the safety numbers describe the code that ships.

HOW THIS FILE FITS INTO THE PROJECT
-----------------------------------
This is the "device zone": the code that runs DURING an emergency, when there
is no internet. It answers two kinds of questions using only the local SQLite
bundle that backend/build_bundle.py produced earlier:

  1. First-aid questions  -> full-text search over vetted entries
  2. "Where do I go?"     -> nearest shelters to a GPS point

It is used from three places:
  - As a command-line tool:  python device/query.py "cant stop the bleeding"
  - By the offline test:     device/tests/test_offline.py
  - By the eval harness:     evals/configs.py imports these same functions,
    so the safety evaluation measures the EXACT code that ships.

Usage (from repo root, works with wifi off):
  python device/query.py "cant stop the bleeding"
  python device/query.py --near 37.87,-122.27
"""
import argparse
import json
import math
import os
import re
import sqlite3
import sys

# Absolute path to the repo root (this file lives in <repo>/device/), and the
# default location of the bundle that build_bundle.py writes.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO, "bundle", "bundle.db")

# Printed before every CLI answer. Required by the project's ground rules:
# nothing here is clinician-reviewed yet.
DISCLAIMER = ("NOT MEDICAL ADVICE — unvetted draft content; does not replace "
              "911 or professional care. If someone is in danger, call 911.")

# Keyword intent router (no ML). If the user's words look like a shelter /
# evacuation question, we route to the shelters table; everything else goes to
# first-aid search. Used by route() below.
SHELTER_PATTERNS = re.compile(
    r"\b(shelter|shelters|evacuat\w*|evac|where (do|can|should) (i|we) go|"
    r"safe place|safest place|refuge|red cross site)\b", re.I)


def connect(db_path=DEFAULT_DB):
    """Open the bundle database read-only and return the connection.

    Called by: main() below, device/tests/test_offline.py, and
    evals/run_evals.py. Read-only mode ("mode=ro") guarantees emergency-time
    code can never modify the bundle. row_factory=sqlite3.Row lets callers
    access columns by name (row["title"]) instead of by index.
    """
    if not os.path.exists(db_path):
        sys.exit(f"No bundle at {db_path}. Run: python backend/build_bundle.py")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_manifest(conn):
    """Return the bundle's manifest (version, freshness dates) as a dict.

    The manifest is the bundle's "label": which region it covers, when it was
    built, and how fresh each dataset is. Every rendered answer must show
    these timestamps. Called by main() and the offline test.
    """
    return {k: v for k, v in conn.execute("SELECT key, value FROM manifest")}


def route(query):
    """Decide which data the question needs: "shelters" or "first_aid".

    A deliberately simple keyword check — no machine learning on the device.
    Called by main() to pick between shelter lookup and first-aid search.
    """
    return "shelters" if SHELTER_PATTERNS.search(query) else "first_aid"


# Filler words that would otherwise dominate the OR fallback ("what do i do").
# Deliberately NOT dropped: not, cant, cannot, stop, out — they carry meaning
# in emergency phrasing ("not breathing", "passed out"). Used by _fts_tokens.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "is", "are", "was", "be",
    "do", "does", "did", "what", "when", "where", "how", "why", "i", "im",
    "me", "my", "we", "our", "you", "your", "he", "him", "his", "she", "her",
    "hes", "shes", "they", "them", "it", "its", "to", "of", "in", "on", "at",
    "for", "with", "from", "by", "so", "just", "now", "please", "think",
}


def _fts_tokens(query):
    """Split the user's question into lowercase search words.

    Drops stopwords and single letters. If EVERYTHING was a stopword (e.g. the
    query "what do i do"), fall back to the unfiltered words so we still
    search with something. Called only by search_first_aid().
    """
    all_tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", query)]
    tokens = [t for t in all_tokens if t not in _STOPWORDS and len(t) > 1]
    return tokens or [t for t in all_tokens if len(t) > 1]


def search_first_aid(conn, query, k=3):
    """Find the k first-aid entries that best match the question.

    This is the heart of the device: SQLite FTS5 full-text search with a
    three-tier cascade, most precise first. Returns a list of sqlite3.Row
    (best match first). Called by main(), the offline test, and
    evals/configs.py (retrieve_fts).

    Tier 1 — exact phrase: the whole query as one quoted phrase. Catches
       negations like "not breathing" that word-by-word matching cannot
       distinguish from "is breathing".
    Tier 2 — AND: every query word must appear somewhere in the entry.
    Tier 3 — OR fallback: any word may match, but results are re-ranked by
       COVERAGE (how many distinct query words the entry matches, plus a
       bonus when adjacent query words appear near each other, e.g.
       "stop ... bleeding"). Without this, one common word like "leg"
       repeated in an unrelated entry would outrank the entry that matches
       most of the query.

    The bm25(...) weights (title=8, scenario=5, steps=1) make an entry that is
    ABOUT the situation outrank one that merely mentions a word in a step.
    Lower bm25 score = better match, hence ORDER BY score ascending.
    """
    tokens = _fts_tokens(query)
    if not tokens:
        return []
    sql = ("SELECT fa.*, fa.rowid AS rowid, "
           "bm25(first_aid_fts, 8.0, 5.0, 1.0) AS score "
           "FROM first_aid_fts "
           "JOIN first_aid fa ON fa.rowid = first_aid_fts.rowid "
           "WHERE first_aid_fts MATCH ? ORDER BY score LIMIT ?")

    # Tiers 1 and 2: try phrase first (only meaningful with 2+ words), then AND.
    candidates = [" AND ".join(tokens)]
    if len(tokens) > 1:
        candidates.insert(0, '"' + " ".join(tokens) + '"')
    for match in candidates:
        rows = conn.execute(sql, (match, k)).fetchall()
        if rows:
            return rows

    # Tier 3: OR fallback with coverage ranking. First count, per entry, how
    # many distinct query words match (weight 1) and how many adjacent word
    # pairs appear within 3 words of each other (weight 2, the NEAR probe).
    coverage = {}
    probes = [(t, 1) for t in tokens]
    probes += [(f"NEAR({a} {b}, 3)", 2) for a, b in zip(tokens, tokens[1:])]
    for probe, weight in probes:
        for (rowid,) in conn.execute(
                "SELECT rowid FROM first_aid_fts WHERE first_aid_fts MATCH ?", (probe,)):
            coverage[rowid] = coverage.get(rowid, 0) + weight
    if not coverage:
        return []
    # Then fetch all OR matches and sort: highest coverage first, bm25 as the
    # tiebreak (negated because Python sorts ascending).
    rows = conn.execute(sql, (" OR ".join(tokens), 25)).fetchall()
    ranked = sorted(rows, key=lambda r: (-coverage.get(r["rowid"], 0), r["score"]))
    return ranked[:k]


def haversine_km(lat1, lon1, lat2, lon2):
    """Distance in km between two GPS points on a sphere (haversine formula).

    Pure math, no network — this is how "nearest shelter" works offline.
    Called only by nearest_shelters().
    """
    r = 6371.0  # Earth's radius in km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_shelters(conn, lat, lon, k=5):
    """Return the k closest shelters as (distance_km, row), nearest first.

    With only ~15 shelters we simply compute the distance to every one and
    sort — no spatial index needed at this scale. Called by main() and the
    offline test.
    """
    rows = conn.execute("SELECT * FROM shelters").fetchall()
    scored = [(haversine_km(lat, lon, r["lat"], r["lon"]), r) for r in rows]
    scored.sort(key=lambda x: x[0])
    return scored[:k]


def _steps_and_donts(row):
    """Decode the JSON-encoded steps and do-not lists stored in one DB row.

    Shared by the two renderers below so the parsing lives in one place.
    """
    return json.loads(row["steps_json"]), json.loads(row["do_not_json"])


def entry_text(row):
    """Flat text of one entry — what a grounded LLM is allowed to answer from.

    Called by evals/configs.py and evals/run_evals.py: this exact text is
    handed to the LLM as its ONLY allowed source, and to the judge as the
    ground truth to check answers against. Not used by the CLI (humans get
    render_entry below instead).
    """
    steps, do_not = _steps_and_donts(row)
    lines = [f"TITLE: {row['title']}", f"APPLIES TO: {row['scenario']}"]
    if row["escalate_911"]:
        lines.append("ESCALATION: Call 911.")
    lines.append("STEPS:")
    lines += [f"{i}. {s}" for i, s in enumerate(steps, 1)]
    lines.append("AVOID:")
    lines += [f"- {d}" for d in do_not]
    return "\n".join(lines)


def render_entry(row, manifest):
    """Human-facing rendering of one entry for the terminal.

    Same content as entry_text() but formatted for a person, and REQUIRED to
    show the review status and freshness timestamp from the manifest. Called
    by main() and the offline test.
    """
    steps, do_not = _steps_and_donts(row)
    out = [f"== {row['title']} ==",
           f"   severity: {row['severity']}"
           + ("   >>> CALL 911 <<<" if row["escalate_911"] else "")]
    out += [f"  {i}. {s}" for i, s in enumerate(steps, 1)]
    out.append("  AVOID:")
    out += [f"   - {d}" for d in do_not]
    out.append(f"  [status: {row['review_status']} | content as of "
               f"{manifest.get('first_aid_freshness', '?')} | bundle "
               f"{manifest.get('bundle_version', '?')}]")
    return "\n".join(out)


def main():
    """Command-line entry point. Parses arguments and routes the request.

    Flow: connect to bundle -> print disclaimer -> then either
      --near LAT,LON  -> nearest shelters (default 5), or
      "question text" -> intent router -> first-aid search (default top 3,
                         best match rendered in full, the rest as "related").
    """
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("query", nargs="?", help="first-aid question")
    p.add_argument("--near", metavar="LAT,LON", help="nearest shelters to a point")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("-k", type=int, help="max results (default: 3 entries, 5 shelters)")
    args = p.parse_args()

    conn = connect(args.db)
    manifest = get_manifest(conn)
    print(DISCLAIMER + "\n")

    if args.near:
        try:
            lat, lon = (float(x) for x in args.near.split(","))
        except ValueError:
            sys.exit("--near expects LAT,LON e.g. --near 37.87,-122.27")
        for dist, r in nearest_shelters(conn, lat, lon, k=args.k or 5):
            print(f"{dist:6.1f} km  [{r['type']:>10}]  {r['name']}")
            print(f"           {r['address']}")
            print(f"           last_verified {r['last_verified']} — {r['capacity_note']}")
        print(f"\n[shelter data as of {manifest.get('shelters_freshness', '?')} | "
              f"bundle {manifest.get('bundle_version', '?')}]")
        return

    if not args.query:
        p.error("give a first-aid question, or --near LAT,LON")

    if route(args.query) == "shelters":
        print("Shelter lookup needs your location. Re-run with --near LAT,LON "
              "(the app will use the GPS blue dot).")
        return

    hits = search_first_aid(conn, args.query, k=args.k or 3)
    if not hits:
        print("No vetted guidance found for that in the offline bundle. "
              "If someone may be in danger, call 911.")
        return
    print(render_entry(hits[0], manifest))
    if len(hits) > 1:
        print("\nrelated: " + ", ".join(r["id"] for r in hits[1:]))


if __name__ == "__main__":
    main()
