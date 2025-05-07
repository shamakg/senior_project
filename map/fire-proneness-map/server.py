from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["http://localhost:3000"])

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
    """Download file from Google Drive using gdown"""
    try:
        # Use the direct download URL format
        url = f"https://drive.google.com/file/d/{file_id}/view"
        logger.info(f"Downloading from: {url}")
        
        # Convert Path to string for gdown
        output_str = str(output_path)
        
        # Use gdown with fuzzy=True for better handling of large files
        gdown.download(url, output_str, fuzzy=True, quiet=False)
        
        # Verify the file was downloaded
        if os.path.exists(output_str) and os.path.getsize(output_str) > 0:
            logger.info("Download completed successfully")
            return True
        else:
            logger.error("Download failed - file is empty or doesn't exist")
            return False
            
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return False

def load_and_cache_data(file_id, cache_filename, chunk_size=50000):
    """Load data from Google Drive and cache it locally using chunks"""
    cache_path = CACHE_DIR / cache_filename
    temp_csv_path = CACHE_DIR / f"temp_{cache_filename}.csv"
    
    # If cached file exists and is not empty, load it
    if cache_path.exists() and cache_path.stat().st_size > 0:
        try:
            logger.info(f"Loading from cache: {cache_filename}")
            df = pd.read_parquet(cache_path, engine='pyarrow')
            # Verify the data is valid
            if df.empty or len(df.columns) < 2:  # Basic validation
                logger.error(f"Invalid data in cache for {cache_filename}")
                if cache_path.exists():
                    cache_path.unlink()
            else:
                logger.info(f"Successfully loaded {cache_filename} from cache")
                logger.info(f"Cache file columns: {df.columns.tolist()}")
                return df
        except Exception as e:
            logger.error(f"Error reading cache {cache_filename}: {e}")
            if cache_path.exists():
                cache_path.unlink()
    
    # If not cached or cache invalid, download from Google Drive
    logger.info(f"Downloading {cache_filename} from Google Drive...")
    
    try:
        # Download to a temporary CSV file first
        if not download_from_drive(file_id, temp_csv_path):
            logger.error(f"Failed to download {cache_filename}")
            return pd.DataFrame()
        
        # Read and process in chunks
        logger.info(f"Processing {cache_filename} in chunks...")
        chunks = []
        for chunk in pd.read_csv(temp_csv_path, chunksize=chunk_size):
            # Validate chunk has data
            if chunk.empty:
                logger.warning(f"Empty chunk found in {cache_filename}")
                continue
                
            # Log chunk info for debugging
            logger.info(f"Processing chunk with columns: {chunk.columns.tolist()}")
            logger.info(f"Chunk shape: {chunk.shape}")
            
            chunks.append(chunk)
            del chunk
        
        if not chunks:
            logger.error(f"No data found in {cache_filename}")
            return pd.DataFrame()
        
        # Combine chunks
        df = pd.concat(chunks, ignore_index=True)
        del chunks  # Clear memory
        
        # Validate final dataframe
        if df.empty:
            logger.error(f"Final dataframe is empty for {cache_filename}")
            return pd.DataFrame()
            
        logger.info(f"Final dataframe columns: {df.columns.tolist()}")
        logger.info(f"Final dataframe shape: {df.shape}")
        
        # Cache the data as parquet
        logger.info(f"Caching {cache_filename}...")
        table = pa.Table.from_pandas(df)
        pq.write_table(table, cache_path, compression='gzip')
        
        # Clean up temporary file
        if temp_csv_path.exists():
            temp_csv_path.unlink()
        
        logger.info(f"Successfully cached {cache_filename}")
        return df
        
    except Exception as e:
        logger.error(f"Error processing {cache_filename}: {e}")
        # Clean up temporary file if it exists
        if temp_csv_path.exists():
            temp_csv_path.unlink()
        return pd.DataFrame()

# Files dictionary with cache filenames and chunk sizes
files = {
    "all_predictions_5years_v2.csv": {
        "id": "1x1jI_OUq7Jl5T3HBIiiHDUZIMI6OLcIV",
        "cache": "predictions_v2.parquet",
        "chunk_size": 50000  # Smaller chunks for large file
    },
    "final_data.csv": {
        "id": "1rQ5QlFXgENzlNPit_ds8RtjegM_YLHU4",
        "cache": "final_data.parquet",
        "chunk_size": 50000  # Smaller chunks for large file
    },
    "fire_data.csv": {
        "id": "1DSTFM2imMKe1iqnANoRkmLQbuMEEcSxm",
        "cache": "fire_data.parquet",
        "chunk_size": 100000  # Larger chunks for small file
    }
}

# Load data with caching
logger.info("Starting data loading process...")
all_predictions_df = load_and_cache_data(
    files["all_predictions_5years_v2.csv"]["id"],
    files["all_predictions_5years_v2.csv"]["cache"],
    files["all_predictions_5years_v2.csv"]["chunk_size"]
)

# Validate predictions dataframe
if not all_predictions_df.empty:
    logger.info("Validating predictions dataframe...")
    logger.info(f"Columns: {all_predictions_df.columns.tolist()}")
    logger.info(f"Shape: {all_predictions_df.shape}")
    
    # Check for required columns
    required_columns = ['grid_id', 'week_start', 'raw_prob']
    missing_columns = [col for col in required_columns if col not in all_predictions_df.columns]
    if missing_columns:
        logger.error(f"Missing required columns in predictions: {missing_columns}")
        all_predictions_df = pd.DataFrame()  # Reset to empty if missing required columns
    else:
        logger.info("All required columns present in predictions")

full = load_and_cache_data(
    files["final_data.csv"]["id"],
    files["final_data.csv"]["cache"],
    files["final_data.csv"]["chunk_size"]
)
full_2 = load_and_cache_data(
    files["fire_data.csv"]["id"],
    files["fire_data.csv"]["cache"],
    files["fire_data.csv"]["chunk_size"]
)

# Verify data loading
if all_predictions_df.empty or full.empty or full_2.empty:
    logger.error("One or more datasets failed to load properly")
    logger.error("Please ensure all Google Drive files are publicly accessible")
    raise Exception("Failed to load required datasets")
else:
    logger.info("All datasets loaded successfully")

# Process predictions only if we have valid data
if not all_predictions_df.empty:
    all_predictions_df["scaled"] = all_predictions_df["raw_prob"]*50

    # Extract the column as a 2D array (needed for sklearn)
    X = all_predictions_df[["scaled"]].values

    # Option 1: Yeo-Johnson (can handle zeros and negatives)
    pt = PowerTransformer(method='yeo-johnson')
    X_transformed = pt.fit_transform(X)

    scaler = MinMaxScaler()
    X_scaled = scaler.fit_transform(X_transformed)

    all_predictions_df["scaled"] = X_scaled
    # all_predictions_df["scaled"] = all_predictions_df["scaled"] ** 0.5

    # import numpy as np

    # Apply log transform to reduce the impact of large outliers
    # all_predictions_df["scaled"] = np.log1p(all_predictions_df["scaled"])

    # min_val = all_predictions_df["scaled"].min()
    # max_val = all_predictions_df["scaled"].max()
    # all_predictions_df["scaled"] = ((all_predictions_df["scaled"] - min_val) / (max_val - min_val) )**0.3

predictions_by_week = {
    week: group.set_index("grid_id")["scaled"].to_dict()
    for week, group in all_predictions_df.groupby("week_start")
}
available_weeks = sorted(predictions_by_week.keys())  # for frontend use


# ──────────────────────────────────────────────────────────────────────────────
# 1) After you build predictions_by_week, perform spatial imputation
# ──────────────────────────────────────────────────────────────────────────────

def generate_grid(bounds, tile_size=1.0 / 69):
    south_west, north_east = bounds
    grid = []
    for lat in np.arange(south_west[0], north_east[0], tile_size):
        for lng in np.arange(south_west[1], north_east[1], tile_size):
            grid.append([[lat, lng], [lat + tile_size, lng + tile_size]])
    return grid


def get_grid_id_from_bounds(bounds):
    lat_center = (bounds[0][0] + bounds[1][0]) / 2
    lng_center = (bounds[0][1] + bounds[1][1]) / 2
    y_index = int((lat_center - LAT_ORIGIN) / TILE_SIZE)
    x_index = int((lng_center - LNG_ORIGIN) / TILE_SIZE)
    return f"{y_index}_{x_index}"

# helper to parse "y_x" → (y:int, x:int)
def parse_grid_id(gid):
    y, x = gid.split("_")
    return int(y), int(x)

# for each week, fill any missing grid_id by neighbor mean
for week, week_map in predictions_by_week.items():
    # build a set of all ids we expect from the full grid
    full_ids = { get_grid_id_from_bounds(b) for b in generate_grid(BUTTE_BOUNDS) }
    # find the "suspicious" missing ones
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
        # else: skip – no vertical neighbors

# ──────────────────────────────────────────────────────────────────────────────



# full = pd.read_csv("final_data.csv", index_col=0) 
full = (
    full.sort_values("week_start")  # or another column that tells which to keep
    .drop_duplicates("grid_id", keep="last")
)
full_feature_map = (
    full
    .set_index("grid_id")
    .drop(columns=["week_start", "fire_occurred"], errors="ignore")
    .to_dict(orient="index")
)



@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "OK"}), 200

@app.route("/api/get-weeks", methods=["GET"])
@cross_origin()
def get_weeks():
    return jsonify({"weeks": available_weeks})

@app.route("/api/predict", methods=["POST", "OPTIONS"])
@cross_origin()
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
@cross_origin()
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
@cross_origin()
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
@cross_origin()
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
@cross_origin()
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
    response.headers["Access-Control-Allow-Origin"] = "http://localhost:3000"
    response.headers.add("Access-Control-Allow-Headers", "Content-Type,Authorization")
    response.headers.add("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    return response

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)  # debug=False for production
