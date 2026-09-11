"use client";

import { useEffect, useRef } from "react";
import * as maplibregl from "maplibre-gl";
import { Protocol } from "pmtiles";
import type { Shelter } from "@/lib/bundle";

let protocolRegistered = false;

type OfflineMapProps = {
  shelters: Shelter[];
  position: { latitude: number; longitude: number } | null;
  onMapError: (message: string) => void;
};

/**
 * Render local shelters and the GPS dot on a MapLibre surface.
 * Called only by the emergency PWA after its local bundle is loaded.
 */
export function OfflineMap({ shelters, position, onMapError }: OfflineMapProps) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!container.current || map.current) return;
    try {
      if (!protocolRegistered) {
        const protocol = new Protocol();
        maplibregl.addProtocol("pmtiles", protocol.tile);
        protocolRegistered = true;
      }
      map.current = new maplibregl.Map({
        container: container.current,
        center: [-122.27, 37.87],
        zoom: 9,
        attributionControl: false,
        // A deliberately local-only style. The PMTiles basemap source is added
        // when bundle/bay-area.pmtiles is supplied; until then shelters and
        // GPS still work without making a remote style or tile request.
        style: { version: 8, sources: {}, layers: [{ id: "ground", type: "background", paint: { "background-color": "#102a43" } }] },
      });
      map.current.on("error", (event) => onMapError(event.error?.message || "The offline map could not load."));
      map.current.on("load", () => {
        const currentMap = map.current;
        if (!currentMap) return;
        currentMap.addSource("shelters", {
          type: "geojson",
          data: {
            type: "FeatureCollection",
            features: shelters.map((shelter) => ({
              type: "Feature",
              properties: { name: shelter.name, type: shelter.type },
              geometry: { type: "Point", coordinates: [shelter.lon, shelter.lat] },
            })),
          },
        });
        currentMap.addLayer({ id: "shelter-points", type: "circle", source: "shelters", paint: { "circle-color": "#f6c453", "circle-radius": 7, "circle-stroke-width": 2, "circle-stroke-color": "#ffffff" } });
      });
    } catch (error) {
      onMapError(error instanceof Error ? error.message : "The offline map could not load.");
    }
    return () => { map.current?.remove(); map.current = null; };
  }, [onMapError, shelters]);

  useEffect(() => {
    const currentMap = map.current;
    if (!currentMap || !position) return;
    const source = currentMap.getSource("position") as maplibregl.GeoJSONSource | undefined;
    const data = { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [position.longitude, position.latitude] } } as GeoJSON.Feature;
    if (source) source.setData(data);
    else if (currentMap.isStyleLoaded()) {
      currentMap.addSource("position", { type: "geojson", data });
      currentMap.addLayer({ id: "position-dot", type: "circle", source: "position", paint: { "circle-color": "#3b82f6", "circle-radius": 9, "circle-stroke-width": 3, "circle-stroke-color": "#ffffff" } });
      currentMap.flyTo({ center: [position.longitude, position.latitude], zoom: 13 });
    }
  }, [position]);

  return <div ref={container} className="map-canvas" aria-label="Offline shelter map" />;
}
