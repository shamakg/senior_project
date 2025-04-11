import React, { useState } from "react";
import Map, { Source, Layer } from "react-map-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { Button } from "@/components/ui/button";

const MAPBOX_TOKEN = "YOUR_MAPBOX_ACCESS_TOKEN";

const FirePronenessMap = () => {
  const [selectedArea, setSelectedArea] = useState(null);
  const [fireScore, setFireScore] = useState(null);

  const handleMapClick = (event) => {
    const [longitude, latitude] = event.lngLat.toArray();
    setSelectedArea({ longitude, latitude });
    fetchFireRiskScore(longitude, latitude);
  };

  const fetchFireRiskScore = async (longitude, latitude) => {
    try {
      const response = await fetch(`/api/fire-risk?lon=${longitude}&lat=${latitude}`);
      const data = await response.json();
      setFireScore(data.score);
    } catch (error) {
      console.error("Error fetching fire risk score:", error);
    }
  };

  return (
    <div className="w-full h-screen relative">
      <Map
        initialViewState={{
          longitude: -121.5,
          latitude: 39.7,
          zoom: 9,
        }}
        style={{ width: "100%", height: "100%" }}
        mapStyle="mapbox://styles/mapbox/streets-v11"
        mapboxAccessToken={MAPBOX_TOKEN}
        onClick={handleMapClick}
      >
        {selectedArea && (
          <Source
            id="selected-area"
            type="geojson"
            data={{
              type: "Feature",
              geometry: {
                type: "Point",
                coordinates: [selectedArea.longitude, selectedArea.latitude],
              },
            }}
          >
            <Layer
              id="point"
              type="circle"
              paint={{ "circle-radius": 6, "circle-color": "red" }}
            />
          </Source>
        )}
      </Map>
      {fireScore !== null && (
        <div className="absolute bottom-5 left-5 bg-white p-4 shadow-lg rounded-lg">
          <p className="text-lg font-bold">Fire Proneness Score: {fireScore}</p>
        </div>
      )}
    </div>
  );
};

export default FirePronenessMap;
