import React, { useState } from "react";
import { MapContainer, TileLayer, Marker, useMapEvents, Polygon } from "react-leaflet"; // Ensure Polygon is imported
import "leaflet/dist/leaflet.css";

const FireRiskMap = () => {
  const [selectedLocation, setSelectedLocation] = useState(null);
  const [selectedTime, setSelectedTime] = useState(0); // State for the time slider

  // Capture click events on the map
  const LocationMarker = () => {
    useMapEvents({
      click(e) {
        setSelectedLocation(e.latlng);
      },
    });

    return selectedLocation ? (
      <Marker position={selectedLocation}></Marker>
    ) : null;
  };

  // Define the polygon for Butte County boundaries
  const butteCountyBounds = [
    [39.4, -121.9], // Southwest corner
    [40.1, -121.9], // Northwest corner
    [40.1, -121.4], // Northeast corner
    [39.4, -121.4], // Southeast corner
  ];

  // Mock data for predictions (adjust based on your data)
  const predictionData = [
    { date: "2025-03-26", riskLevel: "Low" },
    { date: "2025-03-27", riskLevel: "Moderate" },
    { date: "2025-03-28", riskLevel: "High" },
    // Add more prediction data as needed
  ];

  const handleSliderChange = (event) => {
    setSelectedTime(event.target.value); // Set the time based on the slider value
  };

  return (
    <div style={{ position: "relative", height: "100vh", width: "100%" }}>
      <MapContainer
        center={[39.7, -121.6]}
        zoom={10}
        style={{ height: "60%", width: "100%" }} // Reduced map size
        maxBounds={[
          [39.4, -121.9], // Southwest corner (latitude, longitude)
          [40.1, -121.4], // Northeast corner (latitude, longitude)
        ]}
        maxZoom={12}
        minZoom={10}
      >
        {/* OpenStreetMap Tile Layer (Free & No API Key Required) */}
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        />
        {/* Outline of Butte County */}
        {/*    */}
        <LocationMarker />
      </MapContainer>

      {/* Time Slider */}
      <div
        style={{
          position: "absolute",
          top: "70%",
          left: "10%",
          width: "80%",
          padding: "10px",
          background: "white",
          borderRadius: "5px",
          boxShadow: "0 4px 6px rgba(0, 0, 0, 0.1)",
        }}
      >
        <label>Prediction Date: {predictionData[selectedTime].date}</label>
        <input
          type="range"
          min="0"
          max={predictionData.length - 1}
          value={selectedTime}
          onChange={handleSliderChange}
          style={{ width: "100%" }}
        />
        <p>Risk Level: {predictionData[selectedTime].riskLevel}</p>
      </div>
    </div>
  );
};

export default FireRiskMap;
