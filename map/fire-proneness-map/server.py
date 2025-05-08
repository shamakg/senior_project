from flask import Flask, request, jsonify
from flask_cors import CORS
import pandas as pd
import numpy as np
from sklearn.preprocessing import PowerTransformer, MinMaxScaler
import os
import io
import gdown
import pickle
from pathlib import Path
import logging
import pyarrow as pa
from pyarrow.parquet import ParquetWriter
import pyarrow.parquet as pq
import requests
from urllib.parse import urlparse, parse_qs
import tempfile
import subprocess
import shutil
import sys
import gc
from functools import lru_cache
import psutil
import threading
from queue import Queue
import time
from concurrent.futures import ThreadPoolExecutor

# Constants
TILE_SIZE = 1.0 / 69
LAT_ORIGIN = 39.2
LNG_ORIGIN = -122.6
BUTTE_BOUNDS = [
    [39.2, -122.6],
    [39.9, -121.2],
]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": [
            "http://localhost:3000",
            "https://fire-proneness-map-frontend.onrender.com"
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True,
        "max_age": 3600
    }
})

# Create cache directory in a writable location
CACHE_DIR = Path("/tmp/cache")
CACHE_DIR.mkdir(exist_ok=True, parents=True)
logger.info(f"Cache directory created at {CACHE_DIR}")

# Data file configurations with optimized chunk sizes
DATA_FILES = {
    "predictions_v2.csv": {
        "url": "https://github.com/shamakg/senior_project/releases/download/v1.0.0/predictions_v2.csv",
        "chunk_size": 10000  # Reduced chunk size
    },
    "final_data.csv": {
        "url": "https://github.com/shamakg/senior_project/releases/download/v1.0.0/final_data.csv",
        "chunk_size": 10000  # Reduced chunk size
    },
    "fire_data.csv": {
        "url": "https://github.com/shamakg/senior_project/releases/download/v1.0.0/fire_data.csv",
        "chunk_size": 5000  # Reduced chunk size
    }
}

def interpolate_missing_values(predictions, max_distance=2):
    """Interpolate missing grid values using surrounding data, only for squares in the main rectangular grid"""
    # Convert grid IDs to coordinates
    grid_coords = {}
    for grid_id in predictions.keys():
        y, x = map(int, grid_id.split('_'))
        grid_coords[grid_id] = (y, x)
    
    # Find the bounds of the grid
    if not grid_coords:
        return predictions
        
    min_y = min(y for y, _ in grid_coords.values())
    max_y = max(y for y, _ in grid_coords.values())
    min_x = min(x for _, x in grid_coords.values())
    max_x = max(x for _, x in grid_coords.values())
    
    # Find missing grids within the rectangular bounds
    missing_grids = []
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            grid_id = f"{y}_{x}"
            if grid_id not in predictions:
                missing_grids.append((grid_id, y, x))
    
    # Interpolate missing values
    for grid_id, y, x in missing_grids:
        # Find surrounding grids with data
        surrounding_values = []
        for dy in range(-max_distance, max_distance + 1):
            for dx in range(-max_distance, max_distance + 1):
                if dy == 0 and dx == 0:
                    continue
                neighbor_id = f"{y + dy}_{x + dx}"
                if neighbor_id in predictions:
                    # Weight by inverse distance
                    distance = (dy**2 + dx**2)**0.5
                    weight = 1.0 / (distance + 1)  # Add 1 to avoid division by zero
                    surrounding_values.append((predictions[neighbor_id], weight))
        
        if surrounding_values:
            # Calculate weighted average
            total_weight = sum(w for _, w in surrounding_values)
            interpolated_value = sum(v * w for v, w in surrounding_values) / total_weight
            predictions[grid_id] = interpolated_value
    
    return predictions

class DataManager:
    def __init__(self):
        self._predictions_cache = {}
        self._features_cache = {}
        self._fire_data_cache = None
        self._available_weeks = None
        self._lock = threading.Lock()
        self._memory_threshold = 450 * 1024 * 1024  # 450MB threshold
        
    def check_memory(self):
        process = psutil.Process()
        memory_info = process.memory_info()
        current_usage = memory_info.rss
        logger.info(f"Current memory usage: {current_usage / 1024 / 1024:.2f} MB")
        return current_usage < self._memory_threshold

    def clear_old_cache(self):
        with self._lock:
            if not self.check_memory():
                logger.info("Memory threshold exceeded, clearing old cache entries")
                self._predictions_cache.clear()
                self._features_cache.clear()
                gc.collect()
                logger.info(f"After clearing cache: {psutil.Process().memory_info().rss / 1024 / 1024:.2f} MB")

    @lru_cache(maxsize=32)
    def get_predictions_for_week(self, week):
        cache_key = f"predictions_{week}"
        if cache_key in self._predictions_cache:
            return self._predictions_cache[cache_key]
        
        self.clear_old_cache()
        
        try:
            df = pd.read_parquet(CACHE_DIR / "predictions_v2.csv.parquet")
            week_data = df[df["week_start"] == week].copy()
            
            # Process in smaller batches
            batch_size = 5000
            processed_chunks = []
            
            for i in range(0, len(week_data), batch_size):
                chunk = week_data.iloc[i:i+batch_size].copy()
                # Raise raw probabilities to power of 1.2 for better contrast
                chunk["scaled"] = (chunk["raw_prob"] * 500) ** 0.27
                X = chunk[["scaled"]].values
                
                pt = PowerTransformer(method='yeo-johnson')
                X_transformed = pt.fit_transform(X)
                
                scaler = MinMaxScaler()
                X_scaled = scaler.fit_transform(X_transformed)
                
                chunk["scaled"] = X_scaled
                processed_chunks.append(chunk)
                
                del chunk
                gc.collect()
            
            processed_data = pd.concat(processed_chunks, ignore_index=True)
            predictions = processed_data.set_index("grid_id")["scaled"].to_dict()
            
            # Interpolate missing values
            predictions = interpolate_missing_values(predictions)
            
            self._predictions_cache[cache_key] = predictions
            return predictions
            
        except Exception as e:
            logger.error(f"Error loading predictions for week {week}: {e}")
            return {}

    def get_available_weeks(self):
        if self._available_weeks is None:
            try:
                df = pd.read_parquet(CACHE_DIR / "predictions_v2.csv.parquet")
                self._available_weeks = sorted(df["week_start"].unique().tolist())
            except Exception as e:
                logger.error(f"Error loading available weeks: {e}")
                return []
        return self._available_weeks

    def get_features(self, grid_id):
        if grid_id in self._features_cache:
            return self._features_cache[grid_id]
        
        self.clear_old_cache()
        
        try:
            # First try to get features directly
            df = pd.read_parquet(
                CACHE_DIR / "final_data.csv.parquet",
                filters=[('grid_id', '==', grid_id)]
            )
            
            if df.empty:
                # If no direct data, try to interpolate from surrounding grids
                y, x = map(int, grid_id.split('_'))
                surrounding_features = []
                
                # Check surrounding grids in a 2x2 radius
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        if dy == 0 and dx == 0:
                            continue
                        neighbor_id = f"{y + dy}_{x + dx}"
                        try:
                            neighbor_df = pd.read_parquet(
                                CACHE_DIR / "final_data.csv.parquet",
                                filters=[('grid_id', '==', neighbor_id)]
                            )
                            if not neighbor_df.empty:
                                # Weight by inverse distance
                                distance = (dy**2 + dx**2)**0.5
                                weight = 1.0 / (distance + 1)
                                surrounding_features.append((neighbor_df.iloc[-1], weight))
                        except Exception as e:
                            logger.warning(f"Error reading neighbor {neighbor_id}: {e}")
                            continue
                
                if surrounding_features:
                    # Calculate weighted average of features
                    total_weight = sum(w for _, w in surrounding_features)
                    interpolated_features = {}
                    
                    # Get all feature columns (excluding metadata columns)
                    feature_columns = [col for col in surrounding_features[0][0].index 
                                    if col not in ['Unnamed: 0', 'grid_id', 'week_start', 'fire_occurred']]
                    
                    for col in feature_columns:
                        weighted_sum = sum(row[col] * weight for row, weight in surrounding_features)
                        interpolated_features[col] = weighted_sum / total_weight
                    
                    # Convert to DataFrame for consistent processing
                    df = pd.DataFrame([interpolated_features])
                else:
                    logger.warning(f"No features found for grid_id: {grid_id}")
                    return []
            
            # Get the last row and convert to dict
            raw_features = df.iloc[-1].to_dict()
            
            # Remove unwanted columns
            unwanted_columns = ['Unnamed: 0', 'grid_id', 'week_start', 'fire_occurred']
            raw_features = {k: v for k, v in raw_features.items() if k not in unwanted_columns}
            
            # Feature metadata
            feature_metadata = {
                'mean_b4': {
                    'label': 'Red Reflectance (Band 4)',
                    'unit': '',
                    'icon': '🟥',
                    'tooltip': 'Reflectance in red spectrum; lower values suggest vegetation stress.',
                    'style': 'red'
                },
                'mean_b5': {
                    'label': 'Near-Infrared Reflectance (Band 5)',
                    'unit': '',
                    'icon': '🌿',
                    'tooltip': 'Reflectance indicating vegetation health; higher values mean healthier plants.',
                    'style': 'green'
                },
                'mean_b10': {
                    'label': 'Land Surface Temperature (Thermal Infrared)',
                    'unit': 'K',
                    'icon': '🔥',
                    'tooltip': 'Measures heat radiated from the land, indicating surface dryness.',
                    'style': 'orange-red'
                },
                'ndvi': {
                    'label': 'NDVI (Normalized Difference Vegetation Index)',
                    'unit': '',
                    'icon': '🌾',
                    'tooltip': 'Scaled index measuring green vegetation cover across land surfaces.',
                    'style': 'green-yellow'
                },
                'dewpoint_temperature_2m': {
                    'label': 'Dew Point',
                    'unit': 'K',
                    'icon': '🌡️',
                    'tooltip': 'Indicates moisture in the air near the ground surface.',
                    'style': 'light-blue'
                },
                'evaporation_from_bare_soil_sum': {
                    'label': 'Evaporation from Soil',
                    'unit': 'm',
                    'icon': '🌞',
                    'tooltip': 'Represents water loss from bare soil due to evaporation.',
                    'style': 'brown'
                },
                'temperature_2m': {
                    'label': 'Air Temperature',
                    'unit': 'K',
                    'icon': '☀️',
                    'tooltip': 'Temperature two meters above ground; affects vegetation and soil drying.',
                    'style': 'red'
                },
                'total_precipitation_sum': {
                    'label': 'Precipitation Total',
                    'unit': 'm',
                    'icon': '🌧️',
                    'tooltip': 'Cumulative rainfall over time; zero suggests dry fire-prone conditions.',
                    'style': 'blue'
                },
                'volumetric_soil_water_layer_2': {
                    'label': 'Soil Moisture (Layer 2)',
                    'unit': '',
                    'icon': '🌱',
                    'tooltip': 'Water content in mid-level soil layer; influences vegetation dryness.',
                    'style': 'blue-brown'
                }
            }
            # format features with metadata
            formatted_features = []
            for key, value in raw_features.items():
                if key in feature_metadata:
                    metadata = feature_metadata[key]
                    formatted_value = value
                    
                    # special formatting for specific features
                    if key == 'ndvi':
                        formatted_value = round(value / 10000, 3)  # convert to 0-1 scale
                    elif key == 'temperature_2m' or key == 'dewpoint_temperature_2m':
                        # convert kelvin to celsius
                        celsius = value - 273.15
                        formatted_value = f"{value:.3f} K ({celsius:.1f}°C)"
                    elif key == 'evaporation_from_bare_soil_sum' or key == 'total_precipitation_sum':
                        formatted_value = f"{value:.3f} {metadata['unit']}"
                    else:
                        formatted_value = f"{value:.3f} {metadata['unit']}"
                    
                    formatted_features.append({
                        'icon': metadata['icon'],
                        'label': metadata['label'],
                        'value': formatted_value,
                        'tooltip': metadata['tooltip'],
                        'style': metadata['style']
                    })
            
            self._features_cache[grid_id] = formatted_features
            return formatted_features
            
        except Exception as e:
            logger.error(f"error loading features for grid {grid_id}: {str(e)}")
            logger.error(f"memory usage: {psutil.Process().memory_info().rss / 1024 / 1024:.2f} mb")
            return []

    def get_fire_weeks(self):
        if self._fire_data_cache is None:
            try:
                df = pd.read_parquet(CACHE_DIR / "fire_data.csv.parquet")
                self._fire_data_cache = df[df["fire_occurred"] == 1.0]["week_start"].unique().tolist()
            except Exception as e:
                logger.error(f"error loading fire weeks: {e}")
                return []
        return self._fire_data_cache

data_manager = DataManager()

def download_file(url, filename):
    """download a file with streaming and progress tracking"""
    try:
        logger.info(f"downloading {filename}...")
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192 * 4  # increased block size for faster downloads
        downloaded = 0
        
        with open(filename, 'wb') as f:
            for data in response.iter_content(block_size):
                downloaded += len(data)
                f.write(data)
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    if percent % 5 == 0:  # log every 5%
                        logger.info(f"download progress for {filename}: {percent:.1f}%")
        
        # verify file size after download
        actual_size = os.path.getsize(filename)
        if total_size > 0 and actual_size != total_size:
            logger.error(f"download incomplete for {filename}. expected {total_size} bytes, got {actual_size} bytes")
            return False
            
        logger.info(f"successfully downloaded {filename}")
        return True
    except Exception as e:
        logger.error(f"error downloading {filename}: {e}")
        return False

def process_and_cache_file(filename, chunk_size):
    """process and cache a file in chunks"""
    cache_path = CACHE_DIR / f"{filename}.parquet"
    
    if cache_path.exists() and cache_path.stat().st_size > 0:
        logger.info(f"cache exists for {filename}")
        return True
    
    try:
        writer = None
        total_rows = 0
        
        # process in smaller chunks to control memory usage
        for chunk in pd.read_csv(filename, chunksize=5000):
            if chunk.empty:
                continue
                
            if writer is None:
                table = pa.Table.from_pandas(chunk)
                writer = ParquetWriter(str(cache_path), table.schema, compression='snappy')  # using snappy for better performance
            else:
                table = pa.Table.from_pandas(chunk)
            
            writer.write_table(table)
            total_rows += len(chunk)
            
            # free memory
            del table
            del chunk
            gc.collect()
            
            if total_rows % 50000 == 0:
                logger.info(f"processed {total_rows} rows from {filename}")
            
            # check memory usage
            if not data_manager.check_memory():
                logger.warning("memory threshold exceeded during processing")
                if writer:
                    writer.close()
                return False
        
        if writer:
            writer.close()
        
        logger.info(f"successfully cached {filename} with {total_rows} rows")
        return True
        
    except Exception as e:
        logger.error(f"error processing {filename}: {e}")
        if writer:
            writer.close()
        return False

def process_file(filename, config):
    """process a single file with its configuration"""
    if not os.path.exists(filename):
        if not download_file(config["url"], filename):
            return False
    
    if not process_and_cache_file(filename, config["chunk_size"]):
        return False
        
    # remove original csv after successful processing
    if os.path.exists(filename):
        os.remove(filename)
    return True

def ensure_data_files():
    """ensure all required data files exist and are processed"""
    logger.info("starting ensure_data_files...")
    
    # process files in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(process_file, filename, config): filename 
            for filename, config in DATA_FILES.items()
        }
        
        for future in futures:
            filename = futures[future]
            try:
                if not future.result():
                    logger.error(f"failed to process {filename}")
                    return False
            except Exception as e:
                logger.error(f"error processing {filename}: {e}")
                return False
    
    return True

def generate_grid(bounds, tile_size=TILE_SIZE):
    """generate a grid of tiles for the given bounds"""
    south_west, north_east = bounds
    grid = []
    for lat in np.arange(south_west[0], north_east[0], tile_size):
        for lng in np.arange(south_west[1], north_east[1], tile_size):
            grid.append([[lat, lng], [lat + tile_size, lng + tile_size]])
    return grid

def get_grid_id_from_bounds(bounds):
    """get grid id from bounds"""
    lat_center = (bounds[0][0] + bounds[1][0]) / 2
    lng_center = (bounds[0][1] + bounds[1][1]) / 2
    
    y = int((lat_center - LAT_ORIGIN) / TILE_SIZE)
    x = int((lng_center - LNG_ORIGIN) / TILE_SIZE)
    
    return f"{y}_{x}"

# initialize data when app starts
logger.info("="*50)
logger.info("starting server initialization...")
logger.info("="*50)

if not ensure_data_files():
    logger.error("failed to initialize data files")
    raise Exception("failed to initialize data files")

# get port from environment variable
port = int(os.environ.get("PORT", 10000))
logger.info(f"using port: {port}")

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "OK"}), 200

@app.route("/api/get-weeks", methods=["GET"])
def get_weeks():
    return jsonify({"weeks": data_manager.get_available_weeks()})

@app.route("/api/predict", methods=["POST", "OPTIONS"])
def predict():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        week = request.json.get("week")
        bounds = request.json.get("bounds")
        if not bounds or len(bounds) != 2 or not week:
            return jsonify({"error": "invalid bounds or week"}), 400

        grid_id = get_grid_id_from_bounds(bounds)
        predictions = data_manager.get_predictions_for_week(week)
        
        if grid_id not in predictions:
            return jsonify({"prediction": "no data for this grid"}), 200

        calibrated_prob = predictions[grid_id]
        return jsonify({"prediction": str(round(calibrated_prob, 4))}), 200

    except Exception as e:
        logger.error(f"prediction error: {e}")
        return jsonify({"error": "prediction failed"}), 500

@app.route("/api/get-no-data-grids", methods=["POST", "OPTIONS"])
def get_no_data_grids():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        week = request.json.get("week")
        if not week:
            return jsonify({"error": "week not provided"}), 400

        # process in smaller batches to avoid memory issues
        predictions = data_manager.get_predictions_for_week(week)
        all_grids = generate_grid(BUTTE_BOUNDS)
        no_data_grids = []
        
        # process grids in batches of 1000
        batch_size = 1000
        for i in range(0, len(all_grids), batch_size):
            batch = all_grids[i:i + batch_size]
            for bounds in batch:
                grid_id = get_grid_id_from_bounds(bounds)
                if grid_id not in predictions:
                    no_data_grids.append(grid_id)
            
            # force garbage collection after each batch
            if i % (batch_size * 5) == 0:
                gc.collect()
                
        return jsonify({"no_data_grids": no_data_grids}), 200

    except Exception as e:
        logger.error(f"no-data grid error: {e}")
        return jsonify({"error": "failed to get no-data grids", "details": str(e)}), 500

@app.route("/api/get-fire-weeks", methods=["GET"])
def get_fire_weeks():
    try:
        fire_weeks = data_manager.get_fire_weeks()
        return jsonify({"fire_weeks": fire_weeks}), 200
    except Exception as e:
        logger.error(f"fire weeks error: {e}")
        return jsonify({"error": "failed to retrieve fire weeks"}), 500

@app.route("/api/predict-all", methods=["POST", "OPTIONS"])
def predict_all():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        data = request.json or {}
        week = data.get("week")
        tiles = data.get("tiles", [])

        if not week:
            return jsonify({"error": "week not provided"}), 400
        if not isinstance(tiles, list):
            return jsonify({"error": "tiles must be a list"}), 400

        predictions = data_manager.get_predictions_for_week(week)
        results = []
        
        # process tiles in batches of 500
        batch_size = 500
        for i in range(0, len(tiles), batch_size):
            batch = tiles[i:i + batch_size]
            for tile in batch:
                grid_id = tile.get("gridId") or get_grid_id_from_bounds(tile.get("bounds", []))
                pred = predictions.get(grid_id)
                if pred is None:
                    continue
                    
                b = tile["bounds"]
                lat_center = (b[0][0] + b[1][0]) / 2
                lng_center = (b[0][1] + b[1][1]) / 2
                results.append({
                    "grid_id": grid_id,
                    "center": [lat_center, lng_center],
                    "prediction": float(round(pred, 4))
                })
            
            # force garbage collection after each batch
            if i % (batch_size * 5) == 0:
                gc.collect()

        return jsonify({"predictions": results}), 200

    except Exception as e:
        logger.error(f"predict-all error: {e}")
        return jsonify({"error": "failed to process predictions", "details": str(e)}), 500

@app.route("/api/get-features", methods=["POST", "OPTIONS"])
def get_features():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        bounds = request.json.get("bounds")
        if not bounds or len(bounds) != 2:
            return jsonify({"error": "invalid bounds"}), 400

        grid_id = get_grid_id_from_bounds(bounds)
        features = data_manager.get_features(grid_id)
        
        # always return an array, even if empty
        if features is None:
            return jsonify({"features": []}), 200

        return jsonify({"features": features}), 200

    except Exception as e:
        logger.error(f"feature retrieval error: {e}")
        return jsonify({"error": "failed to get features", "details": str(e)}), 500

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    allowed_origins = [
        "http://localhost:3000",
        "https://fire-proneness-map-frontend.onrender.com"
    ]
    if origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Max-Age"] = "3600"
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)
