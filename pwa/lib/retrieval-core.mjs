/**
 * Browser-side port of device/query.py's first-aid retrieval cascade.
 *
 * Called by lib/bundle.ts in the PWA and by scripts/retrieval-parity.mjs.
 * Keeping the algorithm in this dependency-free module lets the parity test
 * prove that the browser ranks the same entry as the Python emergency path.
 */

export const STOPWORDS = new Set([
  "a", "an", "the", "and", "or", "but", "if", "is", "are", "was", "be",
  "do", "does", "did", "what", "when", "where", "how", "why", "i", "im",
  "me", "my", "we", "our", "you", "your", "he", "him", "his", "she", "her",
  "hes", "shes", "they", "them", "it", "its", "to", "of", "in", "on", "at",
  "for", "with", "from", "by", "so", "just", "now", "please", "think",
]);

export function ftsTokens(query) {
  const allTokens = (query.toLowerCase().match(/[a-zA-Z0-9]+/g) || []);
  const tokens = allTokens.filter((token) => !STOPWORDS.has(token) && token.length > 1);
  return tokens.length ? tokens : allTokens.filter((token) => token.length > 1);
}

function rowsFor(db, sql, params) {
  const statement = db.prepare(sql);
  statement.bind(params);
  const rows = [];
  while (statement.step()) rows.push(statement.getAsObject());
  statement.free();
  return rows;
}

const SEARCH_SQL = `
  SELECT fa.*, fa.rowid AS rowid,
         bm25(first_aid_fts, 8.0, 5.0, 1.0) AS score
  FROM first_aid_fts
  JOIN first_aid fa ON fa.rowid = first_aid_fts.rowid
  WHERE first_aid_fts MATCH ?
  ORDER BY score
  LIMIT ?`;

/**
 * Return the same first-aid order as device/query.py's search_first_aid().
 * db is a sql.js-compatible database loaded from the unchanged bundle.db.
 */
export function searchFirstAid(db, query, k = 3) {
  const tokens = ftsTokens(query);
  if (!tokens.length) return [];

  const candidates = [tokens.join(" AND ")];
  if (tokens.length > 1) candidates.unshift(`"${tokens.join(" ")}"`);
  for (const match of candidates) {
    const rows = rowsFor(db, SEARCH_SQL, [match, k]);
    if (rows.length) return rows;
  }

  const coverage = new Map();
  const probes = [
    ...tokens.map((token) => [token, 1]),
    ...tokens.slice(0, -1).map((token, index) => [`NEAR(${token} ${tokens[index + 1]}, 3)`, 2]),
  ];
  for (const [probe, weight] of probes) {
    for (const row of rowsFor(db, "SELECT rowid FROM first_aid_fts WHERE first_aid_fts MATCH ?", [probe])) {
      coverage.set(row.rowid, (coverage.get(row.rowid) || 0) + weight);
    }
  }
  if (!coverage.size) return [];

  return rowsFor(db, SEARCH_SQL, [tokens.join(" OR "), 25])
    .sort((left, right) =>
      (coverage.get(right.rowid) || 0) - (coverage.get(left.rowid) || 0) || left.score - right.score,
    )
    .slice(0, k);
}

/** Return nearby shelters without network access. Called by the PWA map panel. */
export function nearestShelters(db, latitude, longitude, k = 5) {
  const toRadians = (degrees) => (degrees * Math.PI) / 180;
  const distance = (lat, lon) => {
    const deltaLatitude = toRadians(lat - latitude);
    const deltaLongitude = toRadians(lon - longitude);
    const a = Math.sin(deltaLatitude / 2) ** 2
      + Math.cos(toRadians(latitude)) * Math.cos(toRadians(lat)) * Math.sin(deltaLongitude / 2) ** 2;
    return 6371 * 2 * Math.asin(Math.sqrt(a));
  };
  return rowsFor(db, "SELECT * FROM shelters", [])
    .map((shelter) => ({ ...shelter, distanceKm: distance(shelter.lat, shelter.lon) }))
    .sort((left, right) => left.distanceKm - right.distanceKm)
    .slice(0, k);
}
