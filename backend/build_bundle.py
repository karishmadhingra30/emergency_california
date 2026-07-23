"""Build the offline bundle: backend/content/* -> bundle/bundle.db + bundle/manifest.json.

HOW THIS FILE FITS INTO THE PROJECT
-----------------------------------
This is the "backend zone": it runs during CALM time (with internet, on a
laptop or server) and packages all content into one SQLite file — the bundle —
that the device caches and later reads offline during an emergency. Nothing in
this file ever runs on the device.

Inputs  (checked into git, human-editable):
  backend/content/first_aid/*.json   one file per first-aid entry
  backend/content/shelters.json      the seed shelter/evac-point list
  backend/schema.sql                 the database layout

Outputs (gitignored — always rebuilt, never hand-edited):
  bundle/bundle.db       SQLite: first_aid + shelters + FTS index + manifest
  bundle/manifest.json   the same manifest as a standalone file, so future
                         clients (the PWA) can check freshness without
                         opening a database

Deterministic: same content files -> byte-identical bundle. bundle_version is
a hash of the content; created_at derives from the newest content date, not
from the wall clock. Run from repo root: python backend/build_bundle.py
"""
import argparse
import hashlib
import json
import os
import sqlite3
import sys

# Paths, all relative to the repo root (this file lives in <repo>/backend/).
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTENT_DIR = os.path.join(REPO, "backend", "content")
SCHEMA_PATH = os.path.join(REPO, "backend", "schema.sql")
BUNDLE_DIR = os.path.join(REPO, "bundle")

REGION = "bay_area"

# Every content file must carry exactly these fields — the loaders below fail
# the build loudly if one is missing, so a half-written entry can never ship.
FIRST_AID_FIELDS = ["id", "title", "scenario", "disaster_type", "severity",
                    "escalate_911", "steps", "do_not", "source", "last_updated",
                    "review_status"]
SHELTER_FIELDS = ["id", "name", "lat", "lon", "address", "type",
                  "capacity_note", "source", "last_verified"]


def load_first_aid():
    """Read and validate every first-aid JSON file, sorted by filename.

    Sorting matters: identical input order on every build is part of what
    makes the bundle byte-identical across rebuilds. Called by build().
    """
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
        # The filename IS the entry id (fa_burns.json -> id "fa_burns") so the
        # two can never drift apart.
        if e["id"] != fname[:-5]:
            sys.exit(f"ERROR {fname}: id '{e['id']}' does not match filename")
        entries.append(e)
    return entries


def load_shelters():
    """Read and validate the shelter list, sorted by id (determinism again).

    Called by build().
    """
    with open(os.path.join(CONTENT_DIR, "shelters.json")) as f:
        shelters = json.load(f)
    for s in shelters:
        missing = [k for k in SHELTER_FIELDS if k not in s]
        if missing:
            sys.exit(f"ERROR shelter {s.get('id', '?')}: missing fields {missing}")
    return sorted(shelters, key=lambda s: s["id"])


def content_hash(entries, shelters):
    """Fingerprint of ALL content -> the bundle_version string.

    If any content changes, the version changes; if nothing changed, rebuilds
    produce the same version. sort_keys makes the JSON serialization stable.
    Called by build().
    """
    blob = json.dumps({"first_aid": entries, "shelters": shelters},
                      sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def build(built_at=None):
    """The whole pipeline: load content -> create DB -> write both manifests.

    Called by the __main__ block below. Steps:
      1. Load + validate content files.
      2. Compute the manifest (version hash, per-dataset freshness dates).
      3. Create a fresh bundle.db from schema.sql and insert everything.
         The FTS search index fills itself via the triggers in the schema.
      4. Write manifest.json FROM THE SAME DICT as the manifest table, so the
         two can never disagree.
    """
    entries = load_first_aid()
    shelters = load_shelters()

    # Freshness = the newest date in each dataset. The device shows these
    # timestamps with every answer so users know how old the data is.
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

    # Always start from a clean file — a rebuild replaces, never appends.
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
             # steps_text: the steps+do_nots flattened to plain text, which is
             # what the FTS index actually searches (see schema.sql).
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
    conn.execute("VACUUM")  # normalize the file layout -> stable bytes
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
