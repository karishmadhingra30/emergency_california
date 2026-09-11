"use client";

import initSqlJs from "fts5-sql-bundle/dist/sql-wasm.js";
import { nearestShelters, searchFirstAid } from "./retrieval-core.mjs";

export type FirstAidEntry = Record<string, unknown>;
export type Shelter = Record<string, unknown> & { distanceKm: number };
export type Manifest = Record<string, string>;

type Statement = { step: () => boolean; getAsObject: () => Record<string, unknown>; free: () => void };
type Database = { prepare: (sql: string) => Statement };
type SqlJs = { Database: new (data: Uint8Array) => Database };

let databasePromise: Promise<Database> | undefined;

/** Load the read-only emergency bundle from this app's local static assets. */
export function loadDatabase() {
  if (!databasePromise) {
    databasePromise = (async () => {
      const [SQL, response] = await Promise.all([
        initSqlJs({ locateFile: () => "/vendor/sql-wasm.wasm" }),
        fetch("/bundle/bundle.db", { cache: "force-cache" }),
      ]);
      if (!response.ok) throw new Error("The offline guidance bundle is not available yet.");
      return new (SQL as SqlJs).Database(new Uint8Array(await response.arrayBuffer()));
    })();
  }
  return databasePromise;
}

/** Read the manifest from the same local bundle the UI renders. */
export async function loadManifest(): Promise<Manifest> {
  const db = await loadDatabase();
  const statement = db.prepare("SELECT key, value FROM manifest");
  const manifest: Manifest = {};
  while (statement.step()) {
    const row = statement.getAsObject() as { key: string; value: string };
    manifest[row.key] = row.value;
  }
  statement.free();
  return manifest;
}

export async function findFirstAid(query: string): Promise<FirstAidEntry[]> {
  return searchFirstAid(await loadDatabase(), query) as FirstAidEntry[];
}

export async function findShelters(latitude: number, longitude: number): Promise<Shelter[]> {
  return nearestShelters(await loadDatabase(), latitude, longitude) as Shelter[];
}
