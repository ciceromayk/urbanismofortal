/*
Protótipo mínimo: React + MapLibre GL + GeoJSON de zoneamento (exemplo)
Como usar:
1) Crie um novo projeto com Vite: `npm create vite@latest prototipo-maplibre -- --template react-ts`
2) Copie este arquivo para `src/App.tsx` substituindo o existente.
3) Instale dependências:
   npm install maplibre-gl @types/maplibre-gl turf
   (tailwind é opcional. este protótipo inclui CSS simples)
4) Rode: npm install && npm run dev

O componente inicializa um mapa MapLibre, carrega uma camada base raster OSM e adiciona
uma camada GeoJSON embutida (exemplo de zoneamento). Clique em um polígono para ver
propriedades e um cálculo rápido de viabilidade (área * coeficiente simplificado).
*/

import React, { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import * as turf from "@turf/turf";
import "maplibre-gl/dist/maplibre-gl.css";

// Exemplo simplificado de GeoJSON de zoneamento (substitua pelos dados oficiais)
const ZONES_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: {
        id: "Z-001",
        zone: "ZE5",
        coeficiente: 3.0,
        uso: "Residencial",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-38.5190, -3.7285],
            [-38.5175, -3.7285],
            [-38.5175, -3.7270],
            [-38.5190, -3.7270],
            [-38.5190, -3.7285]
          ]
        ]
      }
    },
    {
      type: "Feature",
      properties: {
        id: "Z-002",
        zone: "ZE3",
        coeficiente: 1.5,
        uso: "Comercial",
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-38.5205, -3.7292],
            [-38.5188, -3.7292],
            [-38.5188, -3.7276],
            [-38.5205, -3.7276],
            [-38.5205, -3.7292]
          ]
        ]
      }
    }
  ]
};

export default function App(): JSX.Element {
  const mapContainer = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [selectedInfo, setSelectedInfo] = useState<string | null>(null);

  useEffect(() => {
    if (mapRef.current) return; // só inicializa uma vez

    const map = new maplibregl.Map({
      container: mapContainer.current as string | HTMLElement,
      style: {
        version: 8,
        sources: {
          osm_raster: {
            type: "raster",
            tiles: ["https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256
          }
        },
        layers: [
          {
            id: "osm_raster",
            type: "raster",
            source: "osm_raster"
          }
        ]
      },
      center: [-38.5190, -3.7280], // Fortaleza (approx)
      zoom: 16
    });

    map.on("load", () => {
      // adiciona fonte GeoJSON
      map.addSource("zones", {
        type: "geojson",
        data: ZONES_GEOJSON
      });

      // camada de preenchimento
      map.addLayer({
        id: "zones-fill",
        type: "fill",
        source: "zones",
        paint: {
          "fill-color": ["match", ["get", "zone"], "ZE5", "#7fc97f", "ZE3", "#beaed4", "#cccccc"],
          "fill-opacity": 0.4
        }
      });

      // camada de contorno
      map.addLayer({
        id: "zones-line",
        type: "line",
        source: "zones",
        paint: {
          "line-color": "#333333",
          "line-width": 1
        }
      });

      // interatividade: clique
      map.on("click", "zones-fill", (e) => {
        if (!e.features || !e.features[0]) return;
        const feat = e.features[0];
        const props: any = feat.properties || {};

        // calcula área com turf (em m2) - transformar coords para polygon
        const area = turf.area(feat as turf.helpers.Feature);

        // Viabilidade simplificada: área * coeficiente = área construída possível
        const coef = parseFloat(props.coeficiente) || 1.0;
        const builtArea = (area * coef);

        const info = `ID: ${props.id} | Zona: ${props.zone} | Uso: ${props.uso} | Área: ${area.toFixed(1)} m² | Coef: ${coef} | Área potencial construída: ${builtArea.toFixed(1)} m²`;
        setSelectedInfo(info);

        // popup opcional
        new maplibregl.Popup()
          .setLngLat((e.lngLat as maplibregl.LngLat))
          .setHTML(`<pre style="font-size:12px">${info}</pre>`)
          .addTo(map);
      });

      map.on("mouseenter", "zones-fill", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "zones-fill", () => {
        map.getCanvas().style.cursor = "";
      });
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  return (
    <div className="h-screen w-screen flex flex-col" style={{fontFamily: 'Inter, system-ui'}}>
      <header className="p-3 shadow-md bg-white z-10">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <h1 className="text-lg font-semibold">Protótipo - Análise Imobiliária (Fortaleza)</h1>
          <div className="text-sm text-gray-600">MapLibre + GeoJSON de zoneamento (exemplo)</div>
        </div>
      </header>

      <div className="flex-1 relative">
        <div ref={mapContainer} id="map" style={{ position: 'absolute', top: 0, bottom: 0, width: '100%' }} />

        <aside style={{ position: 'absolute', right: 12, top: 80, width: 360, maxWidth: '38%', background: 'rgba(255,255,255,0.95)', padding: 12, borderRadius: 8, boxShadow: '0 6px 18px rgba(0,0,0,0.12)'}}>
          <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600 }}>Informações do lote</h2>
          <div style={{ marginTop: 8, fontSize: 13 }}>
            {selectedInfo ? (
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{selectedInfo}</pre>
            ) : (
              <div>Clique em uma área de zoneamento para ver informações e cálculo simplificado.</div>
            )}
          </div>

          <div style={{ marginTop: 12 }}>
            <button onClick={() => {
              // exemplo: exportar GeoJSON atual
              const data = mapRef.current?.getSource('zones') as maplibregl.GeoJSONSource | undefined;
              if (!data) return alert('Fonte não encontrada.');
              const d = (data as any)._data || ZONES_GEOJSON;
              const blob = new Blob([JSON.stringify(d)], { type: 'application/json' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = 'zones_export.geojson';
              a.click();
              URL.revokeObjectURL(url);
            }}>Exportar GeoJSON</button>
          </div>
        </aside>
      </div>
    </div>
  );
}