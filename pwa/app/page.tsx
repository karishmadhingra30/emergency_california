"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Cross, LocateFixed, MapPin, Search, ShieldAlert } from "lucide-react";
import { OfflineMap } from "@/components/offline-map";
import { findFirstAid, findShelters, loadManifest, type FirstAidEntry, type Manifest, type Shelter } from "@/lib/bundle";

type Position = { latitude: number; longitude: number };
const DISCLAIMER = "NOT MEDICAL ADVICE — unvetted draft content; does not replace 911 or professional care. If someone is in danger, call 911.";
type ModelContext = { registerTool: (tool: { name: string; title: string; description: string; inputSchema: object; annotations: object; execute: (input: unknown) => Promise<object> }, options: { signal: AbortSignal }) => void | Promise<void> };

function stringValue(entry: FirstAidEntry, key: string) { return typeof entry[key] === "string" ? entry[key] as string : ""; }
function listValue(entry: FirstAidEntry, key: string) { try { return JSON.parse(stringValue(entry, key)) as string[]; } catch { return []; } }

/** The Stage 1 emergency surface. It calls only browser APIs and local bundle files after installation. */
export default function Home() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<FirstAidEntry | null>(null);
  const [related, setRelated] = useState<FirstAidEntry[]>([]);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [shelters, setShelters] = useState<Shelter[]>([]);
  const [position, setPosition] = useState<Position | null>(null);
  const [status, setStatus] = useState("Loading your offline emergency bundle…");
  const [mapError, setMapError] = useState("");

  useEffect(() => {
    Promise.all([loadManifest(), findShelters(37.87, -122.27)]).then(([loadedManifest, nearbyShelters]) => {
      setManifest(loadedManifest); setShelters(nearbyShelters); setStatus("Offline bundle ready");
    }).catch((error) => setStatus(error instanceof Error ? error.message : "Unable to open the offline bundle."));
    if (import.meta.env.PROD && "serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  }, []);

  const runSearch = useCallback(async (term: string) => {
    if (!term.trim()) throw new Error("A search query is required.");
    setStatus("Searching local guidance…");
    try { const hits = await findFirstAid(term); setResult(hits[0] || null); setRelated(hits.slice(1)); const nextStatus = hits.length ? "Guidance found in your offline bundle" : "No matching local guidance found. If someone may be in danger, call 911."; setStatus(nextStatus); return { entryId: hits[0] ? String(hits[0].id) : null, found: hits.length > 0, status: nextStatus }; }
    catch (error) { setStatus(error instanceof Error ? error.message : "Unable to search the offline bundle."); throw error; }
  }, []);

  const search = useCallback(async (event: FormEvent) => { event.preventDefault(); await runSearch(query); }, [query, runSearch]);

  useEffect(() => {
    const context = (document as Document & { modelContext?: ModelContext }).modelContext;
    if (!context) return;
    const lifecycle = new AbortController();
    void Promise.resolve(context.registerTool({
      name: "search_offline_guidance", title: "Search local first-aid guidance",
      description: "Searches the installed emergency bundle only. Use for a first-aid query; it never calls an external service.",
      inputSchema: { type: "object", properties: { query: { type: "string", minLength: 1 } }, required: ["query"], additionalProperties: false },
      annotations: { readOnlyHint: true, untrustedContentHint: false },
      async execute(input) { if (!input || typeof input !== "object" || typeof (input as { query?: unknown }).query !== "string") throw new Error("query must be a string"); return runSearch((input as { query: string }).query); },
    }, { signal: lifecycle.signal })).catch(() => undefined);
    return () => lifecycle.abort();
  }, [runSearch]);

  const useLocation = useCallback(() => {
    if (!navigator.geolocation) { setStatus("This browser does not provide GPS location."); return; }
    setStatus("Finding your location on this device…");
    navigator.geolocation.getCurrentPosition(async ({ coords }) => {
      const nextPosition = { latitude: coords.latitude, longitude: coords.longitude };
      setPosition(nextPosition); setShelters(await findShelters(nextPosition.latitude, nextPosition.longitude)); setStatus("Location updated on this device");
    }, () => setStatus("Location was not available. You can still search the local bundle."), { enableHighAccuracy: true, maximumAge: 15000, timeout: 10000 });
  }, []);

  const title = result ? stringValue(result, "title") : "Search first-aid guidance";
  const steps = result ? listValue(result, "steps_json") : [];
  const donts = result ? listValue(result, "do_not_json") : [];

  return <main>
    <header className="topbar"><div className="brand"><span className="brand-mark"><Cross size={20} strokeWidth={3} /></span><span>EarthQuakePrep</span></div><span className="offline-state"><span className="status-dot" />{status}</span></header>
    <div className="emergency-banner"><ShieldAlert size={20} /><span>{DISCLAIMER}</span><strong>Call 911 in an emergency</strong></div>
    <section className="workspace" aria-label="Emergency response tools">
      <section className="guidance-panel"><p className="eyebrow">OFFLINE FIRST AID</p><h1>What happened?</h1>
        <form className="search-form" onSubmit={search}><label className="sr-only" htmlFor="emergency-query">Describe the emergency</label><Search aria-hidden="true" size={21} /><input id="emergency-query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. cant stop the bleeding" autoComplete="off" /><button type="submit">Search</button></form>
        <article className="guidance-card" aria-live="polite"><div className="entry-heading"><div><p className="eyebrow">{result ? "LOCAL GUIDANCE" : "READY WHEN YOU NEED IT"}</p><h2>{title}</h2></div>{result && stringValue(result, "escalate_911") === "1" && <span className="call-badge">CALL 911</span>}</div>
          {result ? <><p className="scenario">{stringValue(result, "scenario")}</p><ol>{steps.map((step) => <li key={step}>{step}</li>)}</ol><div className="avoid"><strong>Avoid</strong><ul>{donts.map((item) => <li key={item}>{item}</li>)}</ul></div><p className="metadata">{stringValue(result, "review_status")} · Content as of {manifest?.first_aid_freshness || "—"}</p></> : <p className="empty-copy">Search locally stored emergency guidance. Guidance is draft content and must never replace calling 911.</p>}
        </article>{related.length > 0 && <p className="related">Also found: {related.map((entry) => stringValue(entry, "id")).join(", ")}</p>}</section>
      <section className="map-panel"><div className="map-heading"><div><p className="eyebrow">NEAREST LOCAL LOCATIONS</p><h2>Shelters & evacuation points</h2></div><button className="location-button" onClick={useLocation}><LocateFixed size={18} /> Use my location</button></div>
        <div className="map-frame"><OfflineMap shelters={shelters} position={position} onMapError={setMapError} /><div className="map-note">{mapError || "Map base pack: awaiting Bay Area PMTiles. Shelter points and GPS use local data."}</div></div>
        <div className="shelter-list">{shelters.map((shelter) => <article className="shelter" key={String(shelter.id)}><MapPin size={19} /><div><h3>{String(shelter.name)}</h3><p>{shelter.distanceKm.toFixed(1)} km · {String(shelter.type).replace("_", " ")}<br />{String(shelter.address)}</p></div></article>)}</div><p className="metadata">Shelter data as of {manifest?.shelters_freshness || "—"} · approximate seed locations; verify before relying on them.</p>
      </section>
    </section>
  </main>;
}
