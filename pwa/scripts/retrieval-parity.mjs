/** Proves the browser retrieval port keeps the Python path's top result. */
import { readFile } from "node:fs/promises";
import { initSqlJs } from "fts5-sql-bundle";
import { searchFirstAid } from "../lib/retrieval-core.mjs";

const repo = new URL("../../", import.meta.url);
const gold = (await readFile(new URL("evals/gold_set.jsonl", repo), "utf8")).trim().split("\n").map((line) => JSON.parse(line));
const SQL = await initSqlJs({ locateFile: (file) => new URL(`../node_modules/fts5-sql-bundle/dist/${file}`, import.meta.url).pathname });
const db = new SQL.Database(await readFile(new URL("bundle/bundle.db", repo)));
const failures = gold.filter((row) => row.expected_entry_id && searchFirstAid(db, row.query, 1)[0]?.id !== row.expected_entry_id);
db.close();
if (failures.length) throw new Error(`Parity failed: ${failures.map((row) => row.id).join(", ")}`);
console.log(`PARITY PASSED — ${gold.filter((row) => row.expected_entry_id).length} answerable rows match Python top-1`);
