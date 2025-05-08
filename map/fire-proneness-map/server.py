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
    r"/api/*": {
        "origins": [
            "https://fire-proneness-map-frontend.onrender.com",
            "http://localhost:3000",
            "https://senior-project-gvgp.onrender.com"
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
        "supports_credentials": True
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
                chunk["scaled"] = chunk["raw_prob"] * 50
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
            # Read only the specific grid_id to minimize memory usage
            df = pd.read_parquet(
                CACHE_DIR / "final_data.csv.parquet",
                filters=[('grid_id', '==', grid_id)]
            )
            
            if df.empty:
                logger.warning(f"No features found for grid_id: {grid_id}")
                return None
                
            # Get the last row and convert to dict
            features = df.iloc[-1].to_dict()
            
            # Remove unwanted columns
            unwanted_columns = ['Unnamed: 0', 'grid_id', 'week_start']
            features = {k: v for k, v in features.items() if k not in unwanted_columns}
            
            self._features_cache[grid_id] = features
            return features
        except Exception as e:
            logger.error(f"Error loading features for grid {grid_id}: {str(e)}")
            logger.error(f"Memory usage: {psutil.Process().memory_info().rss / 1024 / 1024:.2f} MB")
            return None

    def get_fire_weeks(self):
        if self._fire_data_cache is None:
            try:
                df = pd.read_parquet(CACHE_DIR / "fire_data.csv.parquet")
                self._fire_data_cache = df[df["fire_occurred"] == 1.0]["week_start"].unique().tolist()
            except Exception as e:
                logger.error(f"Error loading fire weeks: {e}")
                return []
        return self._fire_data_cache

data_manager = DataManager()

def download_file(url, filename):
    """Download a file with streaming and progress tracking"""
    try:
        logger.info(f"Downloading {filename}...")
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192 * 4  # Increased block size for faster downloads
        downloaded = 0
        
        with open(filename, 'wb') as f:
            for data in response.iter_content(block_size):
                downloaded += len(data)
                f.write(data)
                if total_size > 0:
                    percent = (downloaded / total_size) * 100
                    if percent % 5 == 0:  # Log every 5%
                        logger.info(f"Download progress for {filename}: {percent:.1f}%")
        
        # Verify file size after download
        actual_size = os.path.getsize(filename)
        if total_size > 0 and actual_size != total_size:
            logger.error(f"Download incomplete for {filename}. Expected {total_size} bytes, got {actual_size} bytes")
            return False
            
        logger.info(f"Successfully downloaded {filename}")
        return True
    except Exception as e:
        logger.error(f"Error downloading {filename}: {e}")
        return False

def process_and_cache_file(filename, chunk_size):
    """Process and cache a file in chunks"""
    cache_path = CACHE_DIR / f"{filename}.parquet"
    
    if cache_path.exists() and cache_path.stat().st_size > 0:
        logger.info(f"Cache exists for {filename}")
        return True
    
    try:
        writer = None
        total_rows = 0
        
        # Process in smaller chunks to control memory usage
        for chunk in pd.read_csv(filename, chunksize=5000):
            if chunk.empty:
                continue
                
            if writer is None:
                table = pa.Table.from_pandas(chunk)
                writer = ParquetWriter(str(cache_path), table.schema, compression='snappy')  # Using snappy for better performance
            else:
                table = pa.Table.from_pandas(chunk)
            
            writer.write_table(table)
            total_rows += len(chunk)
            
            # Free memory
            del table
            del chunk
            gc.collect()
            
            if total_rows % 50000 == 0:
                logger.info(f"Processed {total_rows} rows from {filename}")
            
            # Check memory usage
            if not data_manager.check_memory():
                logger.warning("Memory threshold exceeded during processing")
                if writer:
                    writer.close()
                return False
        
        if writer:
            writer.close()
        
        logger.info(f"Successfully cached {filename} with {total_rows} rows")
        return True
        
    except Exception as e:
        logger.error(f"Error processing {filename}: {e}")
        if writer:
            writer.close()
        return False

def process_file(filename, config):
    """Process a single file with its configuration"""
    if not os.path.exists(filename):
        if not download_file(config["url"], filename):
            return False
    
    if not process_and_cache_file(filename, config["chunk_size"]):
        return False
        
    # Remove original CSV after successful processing
    if os.path.exists(filename):
        os.remove(filename)
    return True

def ensure_data_files():
    """Ensure all required data files exist and are processed"""
    logger.info("Starting ensure_data_files...")
    
    # Process files in parallel
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(process_file, filename, config): filename 
            for filename, config in DATA_FILES.items()
        }
        
        for future in futures:
            filename = futures[future]
            try:
                if not future.result():
                    logger.error(f"Failed to process {filename}")
                    return False
            except Exception as e:
                logger.error(f"Error processing {filename}: {e}")
                return False
    
    return True

def generate_grid(bounds, tile_size=TILE_SIZE):
    """Generate a grid of tiles for the given bounds"""
    south_west, north_east = bounds
    grid = []
    for lat in np.arange(south_west[0], north_east[0], tile_size):
        for lng in np.arange(south_west[1], north_east[1], tile_size):
            grid.append([[lat, lng], [lat + tile_size, lng + tile_size]])
    return grid

def get_grid_id_from_bounds(bounds):
    """Get grid ID from bounds"""
    lat_center = (bounds[0][0] + bounds[1][0]) / 2
    lng_center = (bounds[0][1] + bounds[1][1]) / 2
    
    y = int((lat_center - LAT_ORIGIN) / TILE_SIZE)
    x = int((lng_center - LNG_ORIGIN) / TILE_SIZE)
    
    return f"{y}_{x}"

# Initialize data when app starts
logger.info("="*50)
logger.info("Starting server initialization...")
logger.info("="*50)

if not ensure_data_files():
    logger.error("Failed to initialize data files")
    raise Exception("Failed to initialize data files")

# Get port from environment variable
port = int(os.environ.get("PORT", 10000))
logger.info(f"Using port: {port}")

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
            return jsonify({"error": "Invalid bounds or week"}), 400

        grid_id = get_grid_id_from_bounds(bounds)
        predictions = data_manager.get_predictions_for_week(week)
        
        if grid_id not in predictions:
            return jsonify({"prediction": "No data for this grid"}), 200

        calibrated_prob = predictions[grid_id]
        return jsonify({"prediction": str(round(calibrated_prob, 4))}), 200

    except Exception as e:
        logger.error(f"Prediction error: {e}")
        return jsonify({"error": "Prediction failed"}), 500

@app.route("/api/get-no-data-grids", methods=["POST", "OPTIONS"])
def get_no_data_grids():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        week = request.json.get("week")
        if not week:
            return jsonify({"error": "Week not provided"}), 400

        predictions = data_manager.get_predictions_for_week(week)
        all_grids = generate_grid(BUTTE_BOUNDS)
        no_data_grids = []
        
        for bounds in all_grids:
            grid_id = get_grid_id_from_bounds(bounds)
            if grid_id not in predictions:
                no_data_grids.append(grid_id)
                
        return jsonify({"no_data_grids": no_data_grids}), 200

    except Exception as e:
        logger.error(f"No-data grid error: {e}")
        return jsonify({"error": "Failed to get no-data grids"}), 500

@app.route("/api/get-fire-weeks", methods=["GET"])
def get_fire_weeks():
    try:
        fire_weeks = data_manager.get_fire_weeks()
        return jsonify({"fire_weeks": fire_weeks}), 200
    except Exception as e:
        logger.error(f"Fire weeks error: {e}")
        return jsonify({"error": "Failed to retrieve fire weeks"}), 500

@app.route("/api/predict-all", methods=["POST", "OPTIONS"])
def predict_all():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json or {}
    week = data.get("week")
    tiles = data.get("tiles", [])

    if not week:
        return jsonify({"error": "Week not provided"}), 400
    if not isinstance(tiles, list):
        return jsonify({"error": "Tiles must be a list"}), 400

    predictions = data_manager.get_predictions_for_week(week)
    results = []

    for tile in tiles:
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

    return jsonify({"predictions": results}), 200

@app.route("/api/get-features", methods=["POST", "OPTIONS"])
def get_features():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        bounds = request.json.get("bounds")
        if not bounds or len(bounds) != 2:
            return jsonify({"error": "Invalid bounds"}), 400

        grid_id = get_grid_id_from_bounds(bounds)
        features = data_manager.get_features(grid_id)
        
        if features is None:
            return jsonify({"features": None}), 200

        return jsonify({"features": features}), 200

    except Exception as e:
        logger.error(f"Feature retrieval error: {e}")
        return jsonify({"error": "Failed to get features"}), 500

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "https://fire-proneness-map-frontend.onrender.com")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    response.headers.add("Access-Control-Allow-Credentials", "true")
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=port)