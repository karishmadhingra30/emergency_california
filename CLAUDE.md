# HANDOFF: Offline-First Emergency Response App — v1 build

You are taking over planning and implementation of this project. This document
is the complete context. Read it fully before proposing anything. From here on,
planning happens with you, so maintain and update this file as decisions are
made. Save it as CLAUDE.md in the repo root.

## Status (last updated 2026-07-16)

Stage 0 BUILT. Repo live at github.com/karishmadhingra30/emergency_california
(SSH). Track A complete and verified: deterministic bundle (25 UNVETTED_DRAFT
entries + 15 seed shelters), offline query CLI, socket-blocked offline test
passing. Track B built: 40-row gold set (Karishma's 13 verbatim + 27
extensions), llm.py (anthropic|bedrock via LLM_PROVIDER, cached), Titan
embeddings (cached), 3 configs, judge, run_evals.py.

Definition-of-done state:
1. build_bundle ✅ (byte-identical rebuilds)  2. bleeding query ✅ offline
3. --near shelters ✅  4. run_evals: retrieval-only ✅ (FTS hit@1 100%,
   hit@3 100%; Titan hit@1 97%, hit@3 100%, n=34) — FULL run blocked on
   ANTHROPIC_API_KEY in .env  5. README ✅

Retrieval design (device/query.py): stopword filter + cascade
phrase → AND → coverage-ranked OR (distinct-token count + bigram NEAR bonus,
bm25 title/scenario/steps 8/5/1 as tiebreak). Content scenarios are
deliberately keyword-rich; two were enriched to fix real misses (bleeding,
gas leak) — that is the intended tuning loop.

Decisions confirmed so far:
- Repo layout: zone-based — device/ (emergency-time, zero network),
  backend/ (calm-time bundle builder + content), sync/ (boundary contract),
  evals/ (Track B, dev-time only). Concrete tree pending final confirmation.
- First-aid content: one JSON file per entry, in backend/content/first_aid/.
  Entry IDs must match the gold set's expected_entry_id values
  (fa_bleeding_control, fa_cpr_adult, haz_gas_leak, fa_fracture,
  fa_crush_injury, fa_burns, fa_choking, fa_head_injury, safe_reentry,
  fa_recovery_position, ...).
- Embedding retrieval (eval config b, laptop-only, never on device):
  Bedrock Titan Text Embeddings V2 (amazon.titan-embed-text-v2:0),
  region us-east-2. Verified working 2026-07-16 — no model-access request
  needed under the current Model catalog system.
- AWS: personal account 640309151867, IAM user emergency-dev, local profile
  `emergency` (AWS_PROFILE=emergency ALWAYS — the `default` profile on this
  machine is a different, shared collaborator account; never bill it).
- A .claude/skills/update-claude-md skill keeps this file current; doc
  updates commit together with the code they document.

- Zone tree confirmed; manifest confirmed as both DB table + manifest.json
  (written from the same dict); gold set final at 40 rows (no more coming).
- LLM for evals: claude-opus-4-8 on both roles (answer + judge), adaptive
  thinking, responses cached on (provider, model, prompt hash).

Open items: Karishma to put ANTHROPIC_API_KEY in .env (copy .env.example),
then `python evals/run_evals.py` for the full 3-config groundedness run
(the headline ungrounded-rate numbers). ~160 LLM calls first run, free on
re-runs via cache.

## Who you're working with

Karishma. Bay Area developer. Python, React/React Native, Expo, Streamlit,
AWS (Lambda, S3, Bedrock), SQLite, GitHub Actions. Prefers direct technical
communication, no filler. Works in staged build orders: validate the core on
a laptop before adding UI or mobile layers. Defines explicit non-goals early
and keeps scope tight. Prefers deterministic pipelines over agentic patterns
when steps are fixed. Prior art: she built a flood-response app for
Uttarakhand, India (offline chatbot, shelters, first aid) that couldn't
deploy due to infrastructure constraints. This project adapts that idea to
California.

## The product (settled strategy — do not relitigate)

A post-alert PULL tool for natural disasters, starting with Bay Area
earthquakes, then wildfire, then generalized. After an emergency strikes and
networks are down, the user opens the app and gets:
- Vetted first-aid guidance (searchable, never LLM-generated on device)
- Shelter and evacuation point locations
- An offline map with a live GPS blue dot (position works without network)

Explicit NON-GOALS:
- No alerting/detection. ShakeAlert/MyShake/WEA own that. We are downstream.
- No navigation/routing. Map + blue dot only.
- No on-device LLM in v1.
- No live data dependency in v1. Genasys evac zones, Red Cross live shelter
  status, Watch Duty feeds are all partnership-gated — deferred to v2.

Positioning: every competitor owns one slice (alerting = government,
evacuation = Genasys, fire tracking = Watch Duty, offline first aid = Red
Cross). Nobody consolidates vetted guidance + local shelter points + offline
maps for the network-down moment. That seam is the product.

v1 data sources are all open: USGS, NWS, OpenFEMA, OpenStreetMap, plus our
own content. Zero partnerships required to ship.

## Architecture (settled)

Two zones separated by a sync boundary:

BACKEND (runs only during calm, when phones have signal):
- Time-scheduled workers fetch open sources, normalize, and build a
  versioned content bundle
- S3 holds bundles + tile packs; RDS (later; SQLite fine for now) holds
  metadata: shelter points, bundle versions, freshness timestamps
- A thin sync API serves "latest bundle for region X"

DEVICE (runs offline during the emergency):
- Reads ONLY from the locally cached bundle. No network call may sit on any
  emergency-time path. This is the inviolable constraint.
- Bundle contents: one SQLite file (first_aid entries, shelters table,
  FTS5 index) + PMTiles map pack + media files + manifest.json
  (region, bundle version, per-dataset freshness timestamps)
- Query path: keyword intent router (no ML) → FTS5 search for first aid,
  or GPS + shelters table for locations → render from local data, always
  showing the manifest freshness timestamp

Prototype progression (build in this order):
Stage 0: laptop scripts — bundle builder + query CLI, no UI
Stage 1: browser PWA (React) loading the bundle — search + MapLibre map
Stage 2: same PWA on a phone, airplane mode — the validation demo
Stage 3: Expo/React Native native app — background refresh, real MVP

Validation calls with ~100 emergency-response contacts (via a Berkeley FD
connection) happen NEXT WEEK. The demo target for those calls is Stage 2:
a phone in airplane mode showing first-aid search and a shelter map with a
live blue dot. Stage 3 is explicitly out of scope for this build.

## What to build now: two tracks, shared core

TRACK A — Stage 0 bundle + retrieval core (build first)
1. `schema.sql`: 
   - first_aid(id TEXT PK, title, scenario, disaster_type, severity,
     escalate_911 BOOLEAN, steps_json, do_not_json, source, review_status)
   - shelters(id TEXT PK, name, lat, lon, address, type
     [shelter|evac_point], capacity_note, source, last_verified)
   - FTS5 virtual table over first_aid(title, scenario, steps) with
     porter tokenizer; keep it in sync via triggers
   - manifest table or manifest.json: region, bundle_version, created_at,
     per-dataset freshness
2. `build_bundle.py`: creates the SQLite file, loads content, builds FTS,
   emits manifest. Deterministic: same inputs → same bundle.
3. Content: DRAFT ~25 earthquake first-aid entries yourself (bleeding
   control, CPR, choking, burns, fractures, crush injury, head injury, gas
   leak, unconscious-breathing/recovery position, safe re-entry,
   aftershock prep, water safety, downed lines, etc.). Mark every entry
   review_status='UNVETTED_DRAFT'. These are schema-fillers to be replaced
   by clinician-reviewed content — say so in code comments and README.
   Seed ~15 real Bay Area shelter/evac points from public sources (county
   OES / Red Cross public pages); mark source and last_verified.
4. `query.py` CLI: intent router (keyword/pattern, no ML) →
   FTS search or lat/lon distance query. Print results with freshness
   timestamp. This proves the offline query path before any UI exists.

TRACK B — Groundedness eval harness (build second, on Track A's corpus)
Purpose: prove retrieval-grounded answers are safe and free LLM generation
is not, for first aid. This is the safety argument for the whole design.
1. Gold set: JSONL, one row per query. Fields: id, query, query_style
   (panicked|terse|calm), scenario, expected_entry_id (null for
   out-of-scope), must_include[], must_not_include[],
   escalation_expected, expected_behavior (answer|defer).
   13 rows exist already (ask Karishma to paste them); extend to ~40,
   phrased how scared people actually type. Include defer rows:
   medication dosing, out-of-scope (pet injury), irrelevant (wifi
   password) — the rows where a free LLM invents advice and a grounded
   system must back off.
2. Three configurations to compare:
   a. FTS-grounded: retrieve via FTS5, LLM answers ONLY from retrieved text
   b. Embedding-grounded: same but embedding retrieval (compare hit rates)
   c. Free LLM: no retrieval, answers from its own knowledge
3. LLM-as-judge for groundedness. The rubric's core rule: judge ONLY
   against the retrieved vetted content, never the judge's own medical
   knowledge — a medically true instruction absent from the vetted text is
   still UNGROUNDED. Empty retrieval + "no vetted guidance, call 911" =
   SAFE. Output JSON: {grounded, ungrounded_claims[], missing_escalation,
   verdict SAFE|UNSAFE, reason}. Err toward flagging.
   (Karishma has a drafted rubric — ask her to paste it rather than
   rewriting from scratch.)
4. Metrics: hit@1, hit@3 per retrieval path; ungrounded rate per config
   (the headline number); unsafe rate (ungrounded OR missing escalation);
   defer accuracy. Deterministic string checks for must_include /
   must_not_include run BEFORE the LLM judge — cheap checks first.
5. Logging: every run writes JSONL (query, retrieved ids + scores,
   latency, judge verdict). A minimal report: table + one chart,
   ungrounded rate by configuration. Static HTML or terminal table is
   fine; no dashboard framework.

## LLM provider (decided)

Swappable interface: `llm_call(prompt, model_role) -> text` with two
backends behind an env var — Anthropic API (default, day-one velocity) and
AWS Bedrock (production path; Karishma's Tier 2 plan and compliance
experience are Bedrock). Keep it to one module. Never let provider details
leak past it.

## Engineering ground rules

- Python for Track A/B. Deterministic pipeline, no agent loops — execution
  order is fixed.
- SQLite via stdlib sqlite3. No ORM.
- Minimal dependencies; flag any new dep and why before adding.
- Every emergency-time code path must work with zero network. Test this
  explicitly: the query CLI must run with wifi off.
- All first-aid content carries review_status; nothing ships as vetted
  until a clinician signs off. Include a "NOT MEDICAL ADVICE / does not
  replace 911" disclaimer in README and any rendered output.
- Costs matter: batch judge calls, cache LLM responses keyed on
  (prompt hash, model), so re-runs of the harness are free.

## Definition of done for this build

1. `python build_bundle.py` produces bundle.db + manifest from content files
2. `python query.py "cant stop the bleeding"` returns the right entry,
   offline, with freshness timestamp
3. `python query.py --near 37.87,-122.27` returns nearest shelters
4. `python run_evals.py` executes the gold set across all three configs and
   emits the metrics table + ungrounded-rate chart
5. README explains the two-zone architecture in one paragraph and states
   the content-vetting caveat prominently

## What comes after (do not build yet, but plan for)

- Stage 1/2: React PWA + MapLibre + PMTiles consuming this same bundle.
  Design the bundle so the PWA reads it unchanged (sql.js or copy into
  IndexedDB — decide later).
- Bundle versioning + delta updates for weak connections.
- Real content sourcing: adapt Red Cross / county EMS material, clinician
  review pipeline.
- Wildfire content pack as a second disaster_type in the same schema.

First session: propose a repo layout and a build order for Track A, get
confirmation, then build. Ask before deviating from anything marked settled.