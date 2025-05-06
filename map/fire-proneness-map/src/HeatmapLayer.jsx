// src/HeatmapLayer.jsx
import { useEffect } from "react";
import { useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet.heat";

export default function HeatmapLayer({ points, options = {} }) {
  const map = useMap();

  useEffect(() => {
    if (!map) return;
    // remove any existing heat layers
    map.eachLayer(layer => {
      if (layer && layer._heat) {
        map.removeLayer(layer);
      }
    });

    if (points.length) {
      const heat = L.heatLayer(points, {
        radius: options.radius || 20,
        blur: options.blur || 15,
        maxZoom: options.maxZoom || 16,
        ...options,
      }).addTo(map);
      // flag so we can remove it next time
      heat._heat = true;
    }
  }, [map, points, options]);

  return null;
}
