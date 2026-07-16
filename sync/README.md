# Sync boundary

The contract between the calm-time backend and the emergency-time device.
v1 keeps it deliberately thin; no code lives here yet.

**Contract:** `GET /bundles/{region}/latest` → the manifest
(`region`, `bundle_version`, `created_at`, per-dataset freshness), plus a URL
for the bundle blob (SQLite file; later also the PMTiles map pack). The device
compares `bundle_version` against its cached copy whenever it has signal and
downloads only on change. Nothing on the device ever calls this during an
emergency — if the fetch never happens, the device serves its last cached
bundle and shows its freshness timestamps.

Stage 0: "sync" is copying `bundle/` to wherever the client runs.
Stage 1/2: the PWA loads the same bundle from static hosting (S3).
Stage 3+: a real endpoint with delta updates for weak connections.
