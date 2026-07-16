"""Emergency-time query path. OFFLINE ONLY — reads bundle/bundle.db, never the
network. This module is both the Stage 0 CLI and the retrieval library that the
eval harness imports, so the safety numbers describe the code that ships.

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

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(REPO, "bundle", "bundle.db")

DISCLAIMER = ("NOT MEDICAL ADVICE — unvetted draft content; does not replace "
              "911 or professional care. If someone is in danger, call 911.")

# Keyword intent router (no ML). Shelter/location intent -> shelters table;
# everything else -> first-aid FTS.
SHELTER_PATTERNS = re.compile(
    r"\b(shelter|shelters|evacuat\w*|evac|where (do|can|should) (i|we) go|"
    r"safe place|safest place|refuge|red cross site)\b", re.I)


def connect(db_path=DEFAULT_DB):
    if not os.path.exists(db_path):
        sys.exit(f"No bundle at {db_path}. Run: python backend/build_bundle.py")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_manifest(conn):
    return {k: v for k, v in conn.execute("SELECT key, value FROM manifest")}


def route(query):
    return "shelters" if SHELTER_PATTERNS.search(query) else "first_aid"


# Filler words that would otherwise dominate the OR fallback ("what do i do").
# Deliberately NOT dropped: not, cant, cannot, stop, out — they carry meaning
# in emergency phrasing ("not breathing", "passed out").
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "is", "are", "was", "be",
    "do", "does", "did", "what", "when", "where", "how", "why", "i", "im",
    "me", "my", "we", "our", "you", "your", "he", "him", "his", "she", "her",
    "hes", "shes", "they", "them", "it", "its", "to", "of", "in", "on", "at",
    "for", "with", "from", "by", "so", "just", "now", "please", "think",
}


def _fts_tokens(query):
    all_tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9]+", query)]
    tokens = [t for t in all_tokens if t not in _STOPWORDS and len(t) > 1]
    return tokens or [t for t in all_tokens if len(t) > 1]


def search_first_aid(conn, query, k=3):
    """FTS5 search. Try AND of all tokens (precise), fall back to OR (recall).
    bm25 weights favor title/scenario over step text so an entry ABOUT the
    situation outranks one that merely mentions a word in a step.
    Returns list of (row, score) — lower bm25 score is better."""
    tokens = _fts_tokens(query)
    if not tokens:
        return []
    sql = ("SELECT fa.*, fa.rowid AS rowid, "
           "bm25(first_aid_fts, 8.0, 5.0, 1.0) AS score "
           "FROM first_aid_fts "
           "JOIN first_aid fa ON fa.rowid = first_aid_fts.rowid "
           "WHERE first_aid_fts MATCH ? ORDER BY score LIMIT ?")
    # Cascade: exact phrase (catches negations like "not breathing" that
    # bag-of-words scoring cannot distinguish), then AND of all tokens.
    candidates = [" AND ".join(tokens)]
    if len(tokens) > 1:
        candidates.insert(0, '"' + " ".join(tokens) + '"')
    for match in candidates:
        rows = conn.execute(sql, (match, k)).fetchall()
        if rows:
            return [(r, r["score"]) for r in rows]

    # OR fallback, ranked by how many DISTINCT query tokens the entry matches,
    # plus a bonus for adjacent query-word pairs appearing near each other
    # ("stop ... bleeding"), with bm25 as tiebreak — otherwise one common word
    # like "leg" repeated in an unrelated entry outranks the entry that
    # matches most of the query.
    coverage = {}
    probes = [(t, 1) for t in tokens]
    probes += [(f"NEAR({a} {b}, 3)", 2) for a, b in zip(tokens, tokens[1:])]
    for probe, weight in probes:
        for (rowid,) in conn.execute(
                "SELECT rowid FROM first_aid_fts WHERE first_aid_fts MATCH ?", (probe,)):
            coverage[rowid] = coverage.get(rowid, 0) + weight
    if not coverage:
        return []
    rows = conn.execute(sql, (" OR ".join(tokens), 25)).fetchall()
    ranked = sorted(rows, key=lambda r: (-coverage.get(r["rowid"], 0), r["score"]))
    return [(r, r["score"]) for r in ranked[:k]]


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_shelters(conn, lat, lon, k=5):
    rows = conn.execute("SELECT * FROM shelters").fetchall()
    scored = [(haversine_km(lat, lon, r["lat"], r["lon"]), r) for r in rows]
    scored.sort(key=lambda x: x[0])
    return scored[:k]


def entry_text(row):
    """Flat text of one entry — what a grounded LLM is allowed to answer from."""
    steps = json.loads(row["steps_json"])
    do_not = json.loads(row["do_not_json"])
    lines = [f"TITLE: {row['title']}", f"APPLIES TO: {row['scenario']}"]
    if row["escalate_911"]:
        lines.append("ESCALATION: Call 911.")
    lines.append("STEPS:")
    lines += [f"{i}. {s}" for i, s in enumerate(steps, 1)]
    lines.append("AVOID:")
    lines += [f"- {d}" for d in do_not]
    return "\n".join(lines)


def render_entry(row, manifest):
    steps = json.loads(row["steps_json"])
    do_not = json.loads(row["do_not_json"])
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
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("query", nargs="?", help="first-aid question")
    p.add_argument("--near", metavar="LAT,LON", help="nearest shelters to a point")
    p.add_argument("--db", default=DEFAULT_DB)
    p.add_argument("-k", type=int, default=3, help="max results")
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

    hits = search_first_aid(conn, args.query, k=args.k)
    if not hits:
        print("No vetted guidance found for that in the offline bundle. "
              "If someone may be in danger, call 911.")
        return
    print(render_entry(hits[0][0], manifest))
    if len(hits) > 1:
        also = ", ".join(r["id"] for r, _ in hits[1:])
        print(f"\nrelated: {also}")


if __name__ == "__main__":
    main()
