-- Offline bundle schema (Stage 0).
--
-- HOW THIS FILE FITS INTO THE PROJECT
-- -----------------------------------
-- backend/build_bundle.py runs this script against a fresh bundle.db, then
-- inserts the content. The device (device/query.py) only ever READS the
-- resulting file. Three ordinary tables + one full-text-search index:
--
--   first_aid      the vetted-guidance entries (one row per JSON file)
--   shelters       shelter and evacuation points with coordinates
--   manifest       key/value metadata about the bundle itself
--   first_aid_fts  the search index over first_aid, kept in sync by triggers
--
-- All first_aid rows are review_status='UNVETTED_DRAFT' schema-fillers until a
-- clinician signs off. Nothing here is medical advice; see README disclaimer.

CREATE TABLE first_aid (
  id            TEXT PRIMARY KEY,          -- e.g. 'fa_bleeding_control'; matches filename
  title         TEXT NOT NULL,
  scenario      TEXT NOT NULL,             -- when this entry applies, keyword-rich for FTS
  disaster_type TEXT NOT NULL,             -- 'earthquake' | 'general' (wildfire later)
  severity      TEXT NOT NULL CHECK (severity IN ('low','medium','high','critical')),
  escalate_911  INTEGER NOT NULL CHECK (escalate_911 IN (0,1)),  -- SQLite has no BOOLEAN
  steps_json    TEXT NOT NULL,             -- JSON array of ordered instruction strings
  do_not_json   TEXT NOT NULL,             -- JSON array of "avoid" strings
  steps_text    TEXT NOT NULL,             -- steps flattened by build_bundle.py, FTS only
  source        TEXT NOT NULL,
  last_updated  TEXT NOT NULL,             -- ISO date, drives dataset freshness
  review_status TEXT NOT NULL              -- 'UNVETTED_DRAFT' until clinician review
);

CREATE TABLE shelters (
  id            TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  lat           REAL NOT NULL,             -- device computes distance to these
  lon           REAL NOT NULL,             --   with the haversine formula, offline
  address       TEXT NOT NULL,
  type          TEXT NOT NULL CHECK (type IN ('shelter','evac_point')),
  capacity_note TEXT,
  source        TEXT NOT NULL,
  last_verified TEXT NOT NULL              -- ISO date, drives dataset freshness
);

-- Bundle metadata (region, version hash, freshness dates). Mirrored to
-- bundle/manifest.json by build_bundle.py from the same dict so the two can
-- never disagree. The device shows these values with every answer.
CREATE TABLE manifest (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Full-text search over first aid. FTS5 is SQLite's built-in search engine:
-- it indexes the three listed columns so MATCH queries are instant.
--   content='first_aid'   -> "external content" mode: the index stores no
--                            copy of the text, it points at the real table
--   tokenize='porter ...' -> porter stemming, so "bleeding" matches "bleed"
CREATE VIRTUAL TABLE first_aid_fts USING fts5(
  title, scenario, steps_text,
  content='first_aid',
  content_rowid='rowid',
  tokenize='porter unicode61'
);

-- External-content FTS tables do NOT update themselves: these three triggers
-- replay every insert/delete/update on first_aid into the index, so the two
-- can never drift apart. (The 'delete' insert form below is FTS5's official
-- way of removing an index entry.)
CREATE TRIGGER first_aid_ai AFTER INSERT ON first_aid BEGIN
  INSERT INTO first_aid_fts(rowid, title, scenario, steps_text)
  VALUES (new.rowid, new.title, new.scenario, new.steps_text);
END;

CREATE TRIGGER first_aid_ad AFTER DELETE ON first_aid BEGIN
  INSERT INTO first_aid_fts(first_aid_fts, rowid, title, scenario, steps_text)
  VALUES ('delete', old.rowid, old.title, old.scenario, old.steps_text);
END;

CREATE TRIGGER first_aid_au AFTER UPDATE ON first_aid BEGIN
  INSERT INTO first_aid_fts(first_aid_fts, rowid, title, scenario, steps_text)
  VALUES ('delete', old.rowid, old.title, old.scenario, old.steps_text);
  INSERT INTO first_aid_fts(rowid, title, scenario, steps_text)
  VALUES (new.rowid, new.title, new.scenario, new.steps_text);
END;
