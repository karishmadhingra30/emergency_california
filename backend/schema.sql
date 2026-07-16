-- Offline bundle schema (Stage 0).
-- All first_aid rows are review_status='UNVETTED_DRAFT' schema-fillers until a
-- clinician signs off. Nothing here is medical advice; see README disclaimer.

CREATE TABLE first_aid (
  id            TEXT PRIMARY KEY,
  title         TEXT NOT NULL,
  scenario      TEXT NOT NULL,             -- when this entry applies, keyword-rich for FTS
  disaster_type TEXT NOT NULL,             -- 'earthquake' | 'general' (wildfire later)
  severity      TEXT NOT NULL CHECK (severity IN ('low','medium','high','critical')),
  escalate_911  INTEGER NOT NULL CHECK (escalate_911 IN (0,1)),
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
  lat           REAL NOT NULL,
  lon           REAL NOT NULL,
  address       TEXT NOT NULL,
  type          TEXT NOT NULL CHECK (type IN ('shelter','evac_point')),
  capacity_note TEXT,
  source        TEXT NOT NULL,
  last_verified TEXT NOT NULL              -- ISO date, drives dataset freshness
);

-- Bundle metadata; mirrored to bundle/manifest.json by build_bundle.py from the
-- same dict so the two can never disagree.
CREATE TABLE manifest (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Full-text search over first aid. External-content FTS5 kept in sync by
-- triggers, porter stemming so "bleeding" matches "bleed".
CREATE VIRTUAL TABLE first_aid_fts USING fts5(
  title, scenario, steps_text,
  content='first_aid',
  content_rowid='rowid',
  tokenize='porter unicode61'
);

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
