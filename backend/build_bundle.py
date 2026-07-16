"""Build the offline bundle: backend/content/* -> bundle/bundle.db + bundle/manifest.json.

Deterministic: same content files -> byte-identical bundle. bundle_version is a
hash of the content; created_at derives from the newest content date, not from
the wall clock. Run from repo root: python backend/build_bundle.py
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(REPO, "backend", "content")
SCHEMA_PATH = os.path.join(REPO, "backend", "schema.sql")
BUNDLE_DIR = os.path.join(REPO, "bundle")

REGION = "bay_area"

FIRST_AID_FIELDS = ["id", "title", "scenario", "disaster_type", "severity",
                    "escalate_911", "steps", "do_not", "source", "last_updated",
                    "review_status"]
SHELTER_FIELDS = ["id", "name", "lat", "lon", "address", "type",
                  "capacity_note", "source", "last_verified"]


def load_first_aid():
    fa_dir = os.path.join(CONTENT_DIR, "first_aid")
    entries = []
    for fname in sorted(os.listdir(fa_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(fa_dir, fname)
        with open(path) as f:
            e = json.load(f)
        missing = [k for k in FIRST_AID_FIELDS if k not in e]
        if missing:
            sys.exit(f"ERROR {fname}: missing fields {missing}")
        if e["id"] != fname[:-5]:
            sys.exit(f"ERROR {fname}: id '{e['id']}' does not match filename")
        entries.append(e)
    return entries


def load_shelters():
    with open(os.path.join(CONTENT_DIR, "shelters.json")) as f:
        shelters = json.load(f)
    for s in shelters:
        missing = [k for k in SHELTER_FIELDS if k not in s]
        if missing:
            sys.exit(f"ERROR shelter {s.get('id', '?')}: missing fields {missing}")
    return sorted(shelters, key=lambda s: s["id"])


def content_hash(entries, shelters):
    blob = json.dumps({"first_aid": entries, "shelters": shelters},
                      sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def build(built_at=None):
    entries = load_first_aid()
    shelters = load_shelters()

    fa_fresh = max(e["last_updated"] for e in entries)
    sh_fresh = max(s["last_verified"] for s in shelters)
    manifest = {
        "region": REGION,
        "bundle_version": content_hash(entries, shelters),
        "created_at": built_at or max(fa_fresh, sh_fresh),
        "first_aid_freshness": fa_fresh,
        "first_aid_count": str(len(entries)),
        "shelters_freshness": sh_fresh,
        "shelters_count": str(len(shelters)),
        "review_status": "UNVETTED_DRAFT — content not clinician-reviewed",
    }

    os.makedirs(BUNDLE_DIR, exist_ok=True)
    db_path = os.path.join(BUNDLE_DIR, "bundle.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    for e in entries:
        conn.execute(
            "INSERT INTO first_aid VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (e["id"], e["title"], e["scenario"], e["disaster_type"],
             e["severity"], 1 if e["escalate_911"] else 0,
             json.dumps(e["steps"]), json.dumps(e["do_not"]),
             " ".join(e["steps"] + e["do_not"]),
             e["source"], e["last_updated"], e["review_status"]))
    for s in shelters:
        conn.execute(
            "INSERT INTO shelters VALUES (?,?,?,?,?,?,?,?,?)",
            (s["id"], s["name"], s["lat"], s["lon"], s["address"], s["type"],
             s["capacity_note"], s["source"], s["last_verified"]))
    for k in sorted(manifest):
        conn.execute("INSERT INTO manifest VALUES (?,?)", (k, manifest[k]))
    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    # manifest.json is written from the SAME dict as the manifest table, so the
    # two can never disagree.
    with open(os.path.join(BUNDLE_DIR, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        f.write("\n")

    print(f"bundle.db: {len(entries)} first-aid entries, {len(shelters)} shelters")
    print(f"bundle_version: {manifest['bundle_version']}  region: {REGION}")
    print(f"freshness: first_aid={fa_fresh} shelters={sh_fresh}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--built-at", help="override created_at (ISO date); default is "
                   "newest content date, keeping builds deterministic")
    args = p.parse_args()
    build(built_at=args.built_at)
