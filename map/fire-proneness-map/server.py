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
import pyarrow.parquet as pq
import requests
from urllib.parse import urlparse, parse_qs
import tempfile
import subprocess
import shutil
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://fire-proneness-map-frontend.onrender.com",
            "http://localhost:3000"
        ],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

TILE_SIZE = 1.0 / 69
LAT_ORIGIN = 39.2
LNG_ORIGIN = -122.6
BUTTE_BOUNDS = [
    [39.2, -122.6],
    [39.9, -121.2],
]

# Create cache directory in a writable location
CACHE_DIR = Path("/tmp/cache")  # Render's /tmp directory is writable
CACHE_DIR.mkdir(exist_ok=True, parents=True)
logger.info(f"Cache directory created at {CACHE_DIR}")

# Data file configurations
DATA_FILES = {
    "predictions_v2.csv": {
        "url": "https://github.com/shamakg/senior_project/releases/download/v1.0.0/predictions_v2.csv",
        "chunk_size": 50000
    },
    "final_data.csv": {
        "url": "https://github.com/shamakg/senior_project/releases/download/v1.0.0/final_data.csv",
        "chunk_size": 50000
    },
    "fire_data.csv": {
        "url": "https://github.com/shamakg/senior_project/releases/download/v1.0.0/fire_data.csv",
        "chunk_size": 100000
    }
}

# Global variables to store processed data
all_predictions_df = None
full = None
full_2 = None
predictions_by_week = {}
available_weeks = []
full_feature_map = {}

def get_direct_download_url(file_id):
    """Get a direct download URL for a Google Drive file"""
    try:
        # First try to get the file info
        url = f"https://drive.google.com/file/d/{file_id}/view"
        response = requests.get(url)
        if response.status_code != 200:
            raise Exception(f"Failed to get file info: {response.status_code}")
        
        # Extract the download URL
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        return download_url
    except Exception as e:
        logger.error(f"Error getting direct download URL: {e}")
        return None

def cleanup_temp_files():
    """Clean up any temporary files created by gdown"""
    try:
        # Clean up gdown's temporary directory if it exists
        gdown_tmp = Path('/tmp/gdown')
        if gdown_tmp.exists():
            shutil.rmtree(gdown_tmp)
            logger.info("Cleaned up gdown temporary files")
    except Exception as e:
        logger.error(f"Error cleaning up temporary files: {e}")

def test_file_access(file_id):
    """Test if a file is accessible via direct URL"""
    url = f"https://drive.google.com/uc?id={file_id}"
    try:
        response = requests.head(url, allow_redirects=True)
        logger.info(f"File access test for {file_id}:")
        logger.info(f"Status code: {response.status_code}")
        logger.info(f"Final URL: {response.url}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error testing file access: {e}")
        return False

def download_from_drive(file_id, output_path):
    """Download file from Google Drive using gdown with specific configuration"""
    try:
        # Convert Path to string for gdown
        output_str = str(output_path)
        
        # Use the file view URL format which works better for public files
        url = f"https://drive.google.com/file/d/{file_id}/view"
        logger.info(f"Attempting download from: {url}")
        
        try:
            # Use gdown with specific configuration for public files
            gdown.download(
                url,
                output_str,
                quiet=False,
                fuzzy=True,
                use_cookies=True,
                verify=True,
                proxy=None,
                speed=None,
                no_check_certificate=False
            )
            
            # Verify download
            if os.path.exists(output_str) and os.path.getsize(output_str) > 0:
                # Verify file content is not HTML
                with open(output_str, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(1024)
                    if '<!DOCTYPE html>' in content or '<html>' in content:
                        logger.error("Downloaded content is HTML instead of data")
                        if os.path.exists(output_str):
                            os.remove(output_str)
                        return False
                
                logger.info(f"Download completed successfully. File size: {os.path.getsize(output_str)} bytes")
                return True
            else:
                logger.error("Download failed - file is empty or doesn't exist")
                return False
                
        except Exception as e:
            logger.error(f"Download error: {str(e)}")
            if os.path.exists(output_str):
                os.remove(output_str)
            return False
            
    except Exception as e:
        logger.error(f"Error in download_from_drive: {str(e)}")
        return False

def download_file(url, filename):
    """Download a file from GitHub Releases"""
    try:
        logger.info(f"Downloading {filename}...")
        response = requests.get(url, stream=True)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        total_size = int(response.headers.get('content-length', 0))
        block_size = 8192  # 8 KB chunks
        
        with open(filename, 'wb') as f:
            for data in response.iter_content(block_size):
                f.write(data)
                
        logger.info(f"Successfully downloaded {filename}")
        return True
    except Exception as e:
        logger.error(f"Error downloading {filename}: {e}")
        return False

def ensure_data_files():
    """Ensure all required data files exist, download if missing"""
    for filename, config in DATA_FILES.items():
        if not os.path.exists(filename):
            logger.info(f"{filename} not found locally, downloading...")
            if not download_file(config["url"], filename):
                raise Exception(f"Failed to download required file: {filename}")
        else:
            logger.info(f"{filename} found locally")

def load_and_cache_data(filename, chunk_size=50000):
    """Load data from local file and cache it using chunks"""
    cache_path = CACHE_DIR / f"{filename}.parquet"
    temp_csv_path = CACHE_DIR / f"temp_{filename}.csv"
    
    # If cached file exists and is not empty, load it
    if cache_path.exists() and cache_path.stat().st_size > 0:
        try:
            logger.info(f"Loading from cache: {filename}")
            df = pd.read_parquet(cache_path, engine='pyarrow')
            # Verify the data is valid
            if df.empty or len(df.columns) < 2:  # Basic validation
                logger.error(f"Invalid data in cache for {filename}")
                if cache_path.exists():
                    cache_path.unlink()
            else:
                logger.info(f"Successfully loaded {filename} from cache")
                logger.info(f"Cache file columns: {df.columns.tolist()}")
                return df
        except Exception as e:
            logger.error(f"Error reading cache {filename}: {e}")
            if cache_path.exists():
                cache_path.unlink()
    
    # If not cached or cache invalid, load from local file
    logger.info(f"Loading {filename} from local file...")
    
    try:
        # Read and process in chunks
        logger.info(f"Processing {filename} in chunks...")
        chunks = []
        for chunk in pd.read_csv(filename, chunksize=chunk_size):
            # Validate chunk has data
            if chunk.empty:
                logger.warning(f"Empty chunk found in {filename}")
                continue
                
            # Log chunk info for debugging
            logger.info(f"Processing chunk with columns: {chunk.columns.tolist()}")
            logger.info(f"Chunk shape: {chunk.shape}")
            
            chunks.append(chunk)
            del chunk
        
        if not chunks:
            logger.error(f"No data found in {filename}")
            return pd.DataFrame()
        
        # Combine chunks
        df = pd.concat(chunks, ignore_index=True)
        del chunks  # Clear memory
        
        # Validate final dataframe
        if df.empty:
            logger.error(f"Final dataframe is empty for {filename}")
            return pd.DataFrame()
            
        logger.info(f"Final dataframe columns: {df.columns.tolist()}")
        logger.info(f"Final dataframe shape: {df.shape}")
        
        # Cache the data as parquet
        logger.info(f"Caching {filename}...")
        table = pa.Table.from_pandas(df)
        pq.write_table(table, cache_path, compression='gzip')
        
        logger.info(f"Successfully cached {filename}")
        return df
        
    except Exception as e:
        logger.error(f"Error processing {filename}: {e}")
        return pd.DataFrame()

# Files dictionary with filenames and chunk sizes
files = {
    "predictions_v2.csv": {
        "chunk_size": 50000  # Smaller chunks for large file
    },
    "final_data.csv": {
        "chunk_size": 50000  # Smaller chunks for large file
    },
    "fire_data.csv": {
        "chunk_size": 100000  # Larger chunks for small file
    }
}

def process_predictions(df):
    """Process predictions dataframe and return processed data"""
    if df.empty:
        return None, None, None
        
    df["scaled"] = df["raw_prob"] * 50
    
    # Extract the column as a 2D array (needed for sklearn)
    X = df[["scaled"]].values
    
    # Apply Yeo-Johnson transformation
    pt = PowerTransformer(method='yeo-johnson')
    X_transformed = pt.fit_transform(X)
    
    # Scale to 0-1 range
    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_transformed)
    
    df["scaled"] = X_scaled
    
    # Create predictions by week
    predictions = {
        week: group.set_index("grid_id")["scaled"].to_dict()
        for week, group in df.groupby("week_start")
    }
    
    # Get available weeks
    weeks = sorted(predictions.keys())
    
    # Perform spatial imputation for each week
    for week, week_map in predictions.items():
        # Build a set of all ids we expect from the full grid
        full_ids = { get_grid_id_from_bounds(b) for b in generate_grid(BUTTE_BOUNDS) }
        # Find the "suspicious" missing ones
        missing_ids = full_ids - set(week_map.keys())

        for gid in missing_ids:
            y, x = parse_grid_id(gid)

            above_id = f"{y-1}_{x}"
            below_id = f"{y+1}_{x}"

            above_val = week_map.get(above_id)
            below_val = week_map.get(below_id)

            if above_val is not None and below_val is not None:
                week_map[gid] = (above_val + below_val) / 2
            elif above_val is not None:
                week_map[gid] = above_val
            elif below_val is not None:
                week_map[gid] = below_val
    
    return df, predictions, weeks

def process_features(df):
    """Process features dataframe and return feature map"""
    if df.empty:
        return None
        
    # Sort and deduplicate
    df = df.sort_values("week_start").drop_duplicates("grid_id", keep="last")
    
    # Create feature map
    feature_map = (
        df.set_index("grid_id")
        .drop(columns=["week_start", "fire_occurred"], errors="ignore")
        .to_dict(orient="index")
    )
    
    return feature_map

def load_all_datasets():
    """Load and validate all datasets."""
    global all_predictions_df, full, full_2, predictions_by_week, available_weeks, full_feature_map
    
    logging.info("Starting data loading process...")
    
    # Load predictions data
    predictions_df = load_and_cache_data("predictions_v2.csv", files["predictions_v2.csv"]["chunk_size"])
    if predictions_df is None or predictions_df.empty:
        logging.error("Failed to load predictions data")
        return False
    
    # Load features data
    features_df = load_and_cache_data("final_data.csv", files["final_data.csv"]["chunk_size"])
    if features_df is None or features_df.empty:
        logging.error("Failed to load features data")
        return False
    
    # Load fire data
    fire_df = load_and_cache_data("fire_data.csv", files["fire_data.csv"]["chunk_size"])
    if fire_df is None or fire_df.empty:
        logging.error("Failed to load fire data")
        return False
    
    # Process predictions
    all_predictions_df, predictions_by_week, available_weeks = process_predictions(predictions_df)
    if all_predictions_df is None:
        logging.error("Failed to process predictions")
        return False
    
    # Process features
    full = features_df
    full_feature_map = process_features(features_df)
    if full_feature_map is None:
        logging.error("Failed to process features")
        return False
    
    # Store fire data
    full_2 = fire_df
    
    logging.info("All datasets loaded and processed successfully")
    return True

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "OK"}), 200

@app.route("/api/get-weeks", methods=["GET"])
def get_weeks():
    return jsonify({"weeks": available_weeks})

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
        week_map = predictions_by_week.get(week, {})
        if grid_id not in week_map:
            return jsonify({"prediction": "No data for this grid"}), 200

        calibrated_prob = week_map[grid_id]

        print(f"Grid ID: {grid_id}, Calibrated Probability: {calibrated_prob}")
        return jsonify({"prediction": str(round(calibrated_prob, 4))}), 200

    except Exception as e:
        print("Prediction error:", e)
        return jsonify({"error": "Prediction failed"}), 500

@app.route("/api/get-no-data-grids", methods=["POST", "OPTIONS"])
def get_no_data_grids():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        week = request.json.get("week")
        if not week:
            return jsonify({"error": "Week not provided"}), 400

        current_week_map = predictions_by_week.get(week, {})
        all_grids = generate_grid(BUTTE_BOUNDS)
        no_data_grids = []
        for bounds in all_grids:
            grid_id = get_grid_id_from_bounds(bounds)
            if grid_id not in current_week_map:
                no_data_grids.append(grid_id)
        return jsonify({"no_data_grids": no_data_grids}), 200

    except Exception as e:
        print("No-data grid error:", e)
        return jsonify({"error": "Failed to get no-data grids"}), 500
    
@app.route("/api/get-fire-weeks", methods=["GET"])
def get_fire_weeks():
    try:
        # full_2 = pd.read_csv("fire_data.csv")  
        fire_weeks = full_2[full_2["fire_occurred"] == 1.0]["week_start"].unique().tolist()
        print("FIRE WEEKS: ", fire_weeks)
        return jsonify({"fire_weeks": fire_weeks}), 200
    except Exception as e:
        print("Fire weeks error:", e)
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

    week_map = predictions_by_week.get(week, {})
    results = []

    for tile in tiles:
        # either use provided gridId or recompute
        grid_id = tile.get("gridId") or get_grid_id_from_bounds(tile.get("bounds", []))
        # look up prediction
        pred = week_map.get(grid_id)
        if pred is None:
            continue
        # compute center
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
        features = full_feature_map.get(grid_id)
        if features is None:
            return jsonify({"features": None}), 200

        return jsonify({"features": features}), 200

    except Exception as e:
        print("Feature retrieval error:", e)
        return jsonify({"error": "Failed to get features"}), 500

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "http://localhost:3000")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

def generate_grid(bounds, tile_size=1.0 / 69):
    """Generate a grid of tiles for the given bounds"""
    south_west, north_east = bounds
    grid = []
    for lat in np.arange(south_west[0], north_east[0], tile_size):
        for lng in np.arange(south_west[1], north_east[1], tile_size):
            grid.append([[lat, lng], [lat + tile_size, lng + tile_size]])
    return grid

def parse_grid_id(gid):
    """Parse grid ID string into y, x coordinates"""
    y, x = gid.split("_")
    return int(y), int(x)

if __name__ == "__main__":
    # Ensure all data files exist before starting
    if not ensure_data_files():
        logging.error("Failed to download required data files from GitHub Releases")
        logging.error("Please check that the files exist in the latest release")
        sys.exit(1)

    # Load and validate all datasets
    if not load_all_datasets():
        logging.error("Failed to load one or more datasets")
        logging.error("Please check the data files and try again")
        sys.exit(1)

    # Start the server
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port)
