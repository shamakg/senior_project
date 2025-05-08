import React, { useState, useEffect } from "react";
import { MapContainer, TileLayer, Rectangle, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import axios from "axios";
import "./App.css"; 
import Slider from 'rc-slider';
import 'rc-slider/assets/index.css';
import { Tooltip } from 'react-tooltip';

const BUTTE_BOUNDS = [
  [39.2, -122.6],
  [39.9, -121.2],
];

const TILE_SIZE = 1.0 / 69;

// Use local server in development, production server otherwise
const API_BASE_URL = process.env.NODE_ENV === 'development' 
  ? "http://localhost:10000"
  : "https://fire-proneness-map-backend.onrender.com";

function generateGrid(bounds) {
  const [southWest, northEast] = bounds;
  const grid = [];
  for (let lat = southWest[0]; lat < northEast[0]; lat += TILE_SIZE) {
    for (let lng = southWest[1]; lng < northEast[1]; lng += TILE_SIZE) {
      grid.push([
        [lat, lng],
        [lat + TILE_SIZE, lng + TILE_SIZE],
      ]);
    }
  }
  return grid;
}

function getGridIdFromBounds(bounds) {
  const latCenter = (bounds[0][0] + bounds[1][0]) / 2;
  const lngCenter = (bounds[0][1] + bounds[1][1]) / 2;

  const yIndex = Math.floor((latCenter - BUTTE_BOUNDS[0][0]) / TILE_SIZE);
  const xIndex = Math.floor((lngCenter - BUTTE_BOUNDS[0][1]) / TILE_SIZE);

  return `${yIndex}_${xIndex}`;
}

function App() {
  const [selectedBounds, setSelectedBounds] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [grid, setGrid] = useState([]);
  const [noDataGrids, setNoDataGrids] = useState(new Set());
  const [features, setFeatures] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [selectedWeek, setSelectedWeek] = useState(null);
  const [availableWeeks, setAvailableWeeks] = useState([]);
  const [heatmapData, setHeatmapData] = useState(() => new Map());
  const [fireWeeks, setFireWeeks] = useState(new Set());
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    setGrid(generateGrid(BUTTE_BOUNDS));
  }, []);

  useEffect(() => {
    const fetchNoDataGrids = async () => {
      let retries = 3;
      while (retries > 0) {
        try {
          const response = await fetch(`${API_BASE_URL}/api/get-no-data-grids`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ week: selectedWeek }),
            credentials: 'include'
          });
    
          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.details || `HTTP error! status: ${response.status}`);
          }
    
          const data = await response.json();
          if (data.error) {
            throw new Error(data.error);
          }
    
          setNoDataGrids(new Set(data.no_data_grids));
          break;
        } catch (error) {
          console.error(`Error fetching no-data grids (attempt ${4-retries}/3):`, error);
          retries--;
          if (retries === 0) {
            setNoDataGrids(new Set());
          } else {
            await new Promise(resolve => setTimeout(resolve, (4-retries) * 1000));
          }
        }
      }
    };
  
    if (selectedWeek) {
      fetchNoDataGrids();
      setSelectedBounds(null);
      setPrediction(null);
      setFeatures(null);
    }
  }, [selectedWeek]);

  useEffect(() => {
    const fetchWeeks = async () => {
      try {
        const res = await axios.get(`${API_BASE_URL}/api/get-weeks`);
        setAvailableWeeks(res.data.weeks);
        setSelectedWeek(res.data.weeks[res.data.weeks.length - 1]);
      } catch (error) {
        console.error("Error fetching weeks:", error);
      }
    };

    const fetchFireWeeks = async () => {
      try {
        const res = await axios.get(`${API_BASE_URL}/api/get-fire-weeks`);
        setFireWeeks(new Set(res.data.fire_weeks));
      } catch (error) {
        console.error("Error fetching fire weeks:", error);
        setFireWeeks(new Set());
      }
    };

    Promise.all([fetchWeeks(), fetchFireWeeks()]).finally(() => {
      setIsLoading(false);
    });
  }, []);

  useEffect(() => {
    if (!selectedWeek || grid.length === 0) return;
  
    setIsLoading(true);
    const fetchNoDataGrids = async () => {
      let retries = 3;
      while (retries > 0) {
        try {
          const response = await fetch(`${API_BASE_URL}/api/get-no-data-grids`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ week: selectedWeek })
          });
    
          if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.details || `HTTP error! status: ${response.status}`);
          }
    
          const data = await response.json();
          if (data.error) {
            throw new Error(data.error);
          }
    
          setNoDataGrids(new Set(data.no_data_grids));
          break;
        } catch (error) {
          console.error(`Error fetching no-data grids (attempt ${4-retries}/3):`, error);
          retries--;
          if (retries === 0) {
            setNoDataGrids(new Set());
          } else {
            await new Promise(resolve => setTimeout(resolve, (4-retries) * 1000));
          }
        }
      }
    };
  
    const fetchHeatmapData = async () => {
      let retries = 3;
      while (retries > 0) {
        try {
          const payload = grid.map((bounds) => ({
            gridId: getGridIdFromBounds(bounds),
            bounds,
          }));
          
          const res = await axios.post(`${API_BASE_URL}/api/predict-all`, {
            week: selectedWeek,
            tiles: payload,
          });
      
          if (res.data.error) {
            throw new Error(res.data.error);
          }
      
          const predictionsMap = new Map();
          res.data.predictions.forEach((p) => {
            predictionsMap.set(p.grid_id, p.prediction);
          });
          setHeatmapData(predictionsMap);
          break;
        } catch (error) {
          console.error(`Error fetching heatmap data (attempt ${4-retries}/3):`, error);
          retries--;
          if (retries === 0) {
            setHeatmapData(new Map());
          } else {
            await new Promise(resolve => setTimeout(resolve, (4-retries) * 1000));
          }
        }
      }
    };
  
    if (selectedWeek) {
      Promise.all([fetchNoDataGrids(), fetchHeatmapData()]).finally(() => {
        setIsLoading(false);
      });
      setSelectedBounds(null);
      setPrediction(null);
      setFeatures(null);
    }
  }, [selectedWeek, grid]);

  // useEffect(() => {
  //   if (availableWeeks.length > 0) {
  //     // pick the last (latest) week
  //     setSelectedWeek(availableWeeks[availableWeeks.length - 1]);
  //   }
  // }, [availableWeeks]);

  const handleTileClick = async (bounds) => {
    setSelectedBounds(bounds);
    setPrediction("Loading...");
    setFeatures(null);
    try {
      const [predRes, featRes] = await Promise.all([
        axios.post(`${API_BASE_URL}/api/predict`, { bounds, week: selectedWeek }),
        axios.post(`${API_BASE_URL}/api/get-features`, { bounds }),
      ]);
      setPrediction(predRes.data.prediction);
      setFeatures(featRes.data.features || {});
    } catch (error) {
      console.error("Prediction or feature fetch error:", error);
      setPrediction("Error predicting fire risk");
    }
  };

  const getPopupCenter = (bounds) => {
    const lat = (bounds[0][0] + bounds[1][0]) / 2;
    const lng = (bounds[0][1] + bounds[1][1]) / 2;
    return [lat, lng];
  };


  const markInterval = 30;

const marks = {};

availableWeeks.forEach((week, i) => {
  const showLabel = i % markInterval === 0;
  const hasFire = fireWeeks.has(week);
  const tooltipText = hasFire ? `There was really a fire here!` : `${week}`;
    marks[i] = {
      label: (
        <div style={{ textAlign: "center", lineHeight: 1.2 }}
        data-tooltip-id="week-tooltip"
          data-tooltip-content={tooltipText}
        >
          {/* Fire icon gets moved up */}
          {hasFire && (
            <img
              title={`There was really a fire here!`}
              src="/vecteezy_fire-icon-on-transparent-background_19787026.png"
              alt="Fire"
              width="35"
              height="20"
              style={{
                display: "block",
                margin: "0 auto",
                marginBottom: 2, // Add some spacing between the icon and text
                position: "relative",
                top: -20, // Move the fire icon up above the slider
              }}
            />
          )}

          {/* Add tick marks if no fire icon is present */}
          {!hasFire && (
            <div
              title={`${week}`}
              style={{
                position: "relative",
                top: -12, // Adjust position of tick mark to align with fire icons
                width: 1.5,
                height: 7, // Height of the tick mark
                backgroundColor: "#d33", // Fire-themed color for tick marks
                margin: "0 auto",
              }}
            />
          )}

          {/* Week label stays where it is */}
          {showLabel && (
            <div style={{ position: "relative", fontSize: 10, color: "#444", marginTop: 1, top: -8, }}>
              {week}
            </div>
          )}
        </div>
      )
    };
});


  

  return (
    <div className="app">
      <header className="app-header">
        <h1>Wildfire Prediction in Butte County</h1>
        <button className="sidebar-toggle" onClick={() => setSidebarOpen(!sidebarOpen)}>
          {sidebarOpen ? "Close Sidebar" : "Show Features"}
        </button>
      </header>
      <div className="week-slider">
        <label htmlFor="week-range"><strong>Select Week:</strong></label>

        <div className="slider-container">
        <Slider
          min={0}
          max={availableWeeks.length - 1}
          marks={marks}
          step={1}
          value={availableWeeks.indexOf(selectedWeek)}
          onChange={(idx) => setSelectedWeek(availableWeeks[idx])}
          dot={false}
          dotStyle={{ display: 'none' }}
          trackStyle={{ backgroundColor: "#d33", height: 6 }}
  handleStyle={{
    borderColor: "black",
    height: 16,
    width: 16,
    marginTop: -5,
    backgroundColor: "#fff"
  }}
  railStyle={{ backgroundColor: "#d33", height: 6 }}
        />
        <Tooltip id="week-tooltip" place="top" style={{ backgroundColor: "#222", color: "#fff", fontSize: "12px", borderRadius: "4px" }} />

          {/* <input
            id="week-range"
            type="range"
            min="0"
            max={availableWeeks.length - 1}
            value={availableWeeks.indexOf(selectedWeek)}
            onChange={(e) => setSelectedWeek(availableWeeks[parseInt(e.target.value)])}
            className="slider"
            onMouseMove={(e) => {
              const index = parseInt(e.target.value);
              const tooltip = document.getElementById("tooltip");
              if (tooltip) {
                tooltip.style.left = `${(index / (availableWeeks.length - 1)) * 100}%`;
                tooltip.innerText = availableWeeks[index];
              }
            }}
          />
          <div id="tooltip" className="slider-tooltip">{selectedWeek}</div>
          <div className="slider-ticks">
            {availableWeeks.map((_, index) => (
              <div
                key={index}
                className={`tick ${index % Math.ceil(availableWeeks.length / 6) === 0 
                  ? "tick-labeled" 
                  : "tick-small"}`}
                style={{ width: "1px", height: "6px", background: "#444" }}

              />
            ))}
          </div>
          <div className="slider-labels">
            {availableWeeks.map((week, index) =>
              index % Math.ceil(availableWeeks.length / 6) === 0 ? (
                <span key={index} className="slider-label">
                  {week}
                </span>
              ) : (
                <span key={index} className="slider-label empty-label" />
              )
            )}
          </div> */}
        </div>
        {/* Fire icons row */}
        {/* <div className="slider-fires">
  {availableWeeks.map((week, index) =>
    fireWeeks.has(week) ? (
      <span
        key={index}
        style={{
          position: "absolute",
          left: `${(index / (availableWeeks.length - 1)) * 100}%`,  // This is the issue
          transform: "translateX(-50%)",  // This centers the icons
          fontSize: "14px",
        }}
      >
        <img src="/vecteezy_fire-icon-on-transparent-background_19787026.png" alt="Fire" width="30" height="16" />
      </span>
    ) : null
  )}
</div> */}
        <div className="week-display">Showing week: <strong>{selectedWeek}</strong></div>
      </div>


      <main className="map-container">
        <MapContainer bounds={BUTTE_BOUNDS} scrollWheelZoom className="leaflet-map">
          <TileLayer
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution="&copy; OpenStreetMap contributors"
          />

          {grid
            .filter((bounds) => {
              const gridId = getGridIdFromBounds(bounds);
              return !noDataGrids.has(gridId); // Only include tiles with data
            })
            .map((bounds,i) => {
              const gridId = getGridIdFromBounds(bounds);
              const pred = heatmapData.get(gridId) ?? 0;
              const rawPred = Math.min(1, Math.max(0, pred));

              // Apply power transformation for better contrast
              const norm = Math.pow(rawPred, 0.4);  // Using 0.4 to compensate for server's 1.2
              
              let r, g, b;
              if (norm < 0.33) {
                // Green to Yellow: from (50, 255, 50) → (255, 255, 50)
                r = 50 + norm * 3 * 205;  // from 50 → 255
                g = 255;
                b = 50;
              } else if (norm < 0.66) {
                // Yellow to Orange: from (255, 255, 50) → (255, 165, 0)
                r = 255;
                g = 255 - (norm - 0.33) * 3 * 90;  // from 255 → 165
                b = 50 - (norm - 0.33) * 3 * 50;   // from 50 → 0
              } else {
                // Orange to Red: from (255, 165, 0) → (255, 0, 0)
                r = 255;
                g = 165 * (1 - (norm - 0.66) * 3);  // from 165 → 0
                b = 0;
              }

              const color = `rgba(${r | 0},${g | 0},${b | 0},0.8)`;
              return (
                <Rectangle
                  key={i}
                  bounds={bounds}
                  pathOptions={{ color, weight:1, fillOpacity:0.7 }}
                  eventHandlers={{ click:()=>handleTileClick(bounds) }}
                />
              );
            })}

          {selectedBounds && prediction && (
            <Popup position={getPopupCenter(selectedBounds)}>
              <div>
                <strong>Fire Proneness:</strong> {prediction}
              </div>
            </Popup>
          )}
        </MapContainer>
        
        {isLoading && (
          <div className="loading-overlay">
            <div className="loading-spinner"></div>
            <div className="loading-text">Loading map data...</div>
          </div>
        )}
      </main>

      {/* Sidebar for features */}
      <div className={`sidebar ${sidebarOpen ? "open" : ""}`}>
        <button className="close-btn" onClick={() => setSidebarOpen(false)}>X</button>
        <h3>Feature Details</h3>
        {features && Array.isArray(features) && features.length > 0 ? (
          <ul className="feature-list">
            {features.map((feature, index) => (
              <li key={index} className={`feature-item ${feature.style}`} data-tooltip-id="feature-tooltip" data-tooltip-content={feature.tooltip}>
                <div className="feature-header">
                  <span className="feature-icon">{feature.icon}</span>
                  <span className="feature-label">{feature.label}</span>
                </div>
                <div className="feature-value">{feature.value}</div>
              </li>
            ))}
          </ul>
        ) : (
          <p>No features available for this location.</p>
        )}
        <Tooltip id="feature-tooltip" place="right" />
      </div>
      <div style={{
        position: 'absolute',
        bottom: 20,
        left: 20,
        padding: 10,
        background: 'white',
        borderRadius: 8,
        boxShadow: '0 0 5px rgba(0,0,0,0.3)',
        fontFamily: 'sans-serif',
        fontSize: 12
      }}>
        <div style={{ marginBottom: 5, fontWeight: 'bold' }}>Fire Risk</div>
        <div style={{
          display: 'flex',
          height: 12,
          width: 150,
          background: 'linear-gradient(to right, yellow, orange, red)',
          marginBottom: 4
        }}></div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>Low</span>
          <span>High</span>
        </div>
      </div>
    </div>
    
    
  );
}

export default App;
