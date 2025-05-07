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

# --- Configuration & Constants ------------------------------------------------
# Tile size: 1 mile ≈ 1/69 degrees
TILE_SIZE = 1.0 / 69
LAT_ORIGIN = 39.2
LNG_ORIGIN = -122.6
BUTTE_BOUNDS = [
    [39.2, -122.6],
    [39.9, -121.2],
]

# Data files (GitHub releases)
DATA_FILES = {
    "predictions_v2.csv": {"url": "https://github.com/shamakg/senior_project/releases/download/v1.0.0/predictions_v2.csv"},
    "final_data.csv":       {"url": "https://github.com/shamakg/senior_project/releases/download/v1.0.0/final_data.csv"},
    "fire_data.csv":        {"url": "https://github.com/shamakg/senior_project/releases/download/v1.0.0/fire_data.csv"},
}

# Per-file chunk sizes for CSV reading
FILE_CHUNKS = {
    "predictions_v2.csv": 50000,
    "final_data.csv":     50000,
    "fire_data.csv":     100000,
}

# Cache directory (writable on Render)
CACHE_DIR = Path("/tmp/cache")
CACHE_DIR.mkdir(exist_ok=True, parents=True)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Flask setup
app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": ["https://fire-proneness-map-frontend.onrender.com", "http://localhost:3000"], "methods": ["GET","POST","OPTIONS"], "allow_headers": ["Content-Type"]}})

# — Global state —
all_predictions_df = None
predictions_by_week = {}
available_weeks = []
full_feature_map = {}
fire_df = None

# --- Utility: Grid logic --------------------------------------------------------
def generate_grid(bounds, tile_size=TILE_SIZE):
    south_west, north_east = bounds
    grid = []
    for lat in np.arange(south_west[0], north_east[0], tile_size):
        for lng in np.arange(south_west[1], north_east[1], tile_size):
            grid.append([[lat, lng], [lat + tile_size, lng + tile_size]])
    return grid

def get_grid_id_from_bounds(bounds):
    lat_center = (bounds[0][0] + bounds[1][0]) / 2
    lng_center = (bounds[0][1] + bounds[1][1]) / 2
    y = int((lat_center - LAT_ORIGIN) / TILE_SIZE)
    x = int((lng_center - LNG_ORIGIN) / TILE_SIZE)
    return f"{y}_{x}"

def parse_grid_id(gid):
    y, x = gid.split("_")
    return int(y), int(x)

# --- Download & caching logic --------------------------------------------------
def download_file(url, dest_path):
    """Download from HTTP URL with streaming."""
    try:
        logger.info(f"Downloading {url} to {dest_path}")
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        logger.error(f"download_file error: {e}")
        return False

# Note: we keep your original gdown logic intact
def download_from_drive(file_id, output_path):
    """Download file from Google Drive using gdown with specific configuration"""
    try:
        url = f"https://drive.google.com/file/d/{file_id}/view"
        gdown.download(
            url,
            str(output_path),
            quiet=False,
            fuzzy=True,
            use_cookies=True,
            verify=True,
            proxy=None,
            speed=None,
            no_check_certificate=False
        )
        if output_path.exists() and output_path.stat().st_size > 0:
            with open(output_path, 'r', encoding='utf-8', errors='ignore') as f:
                head = f.read(1024)
                if '<!DOCTYPE html>' in head or '<html>' in head:
                    output_path.unlink()
                    return False
            return True
        else:
            return False
    except Exception as e:
        logger.error(f"download_from_drive error: {e}")
        return False

def ensure_data_files():
    """Ensure all required data files exist using GitHub Releases download logic"""
    logger.info("Starting ensure_data_files...")
    for filename, config in DATA_FILES.items():
        logger.info(f"Checking file: {filename}")
        if not os.path.exists(filename):
            logger.info(f"{filename} not found locally, downloading from {config['url']}...")
            if not download_file(config['url'], filename):
                logger.error(f"Failed to download required file: {filename}")
                return False
            logger.info(f"Successfully downloaded {filename}")
        else:
            logger.info(f"{filename} found locally")
    return True

# --- Data loading & processing -----------------------------------------------
def load_and_cache_data(fname):
    cache_file = CACHE_DIR / f"{fname}.parquet"
    if cache_file.exists():
        try:
            return pd.read_parquet(cache_file)
        except:
            cache_file.unlink()
    chunks = []
    for chunk in pd.read_csv(fname, chunksize=FILE_CHUNKS[fname]):
        chunks.append(chunk)
    df = pd.concat(chunks, ignore_index=True)
    df.to_parquet(cache_file, compression='gzip')
    return df

def process_predictions(df):
    df['scaled'] = df['raw_prob'] * 50
    X = df[['scaled']].values
    pt = PowerTransformer()
    df['scaled'] = MinMaxScaler().fit_transform(pt.fit_transform(X))
    preds = {w: g.set_index('grid_id')['scaled'].to_dict() for w, g in df.groupby('week_start')}
    weeks = sorted(preds)
    full_ids = {get_grid_id_from_bounds(b) for b in generate_grid(BUTTE_BOUNDS)}
    for w, m in preds.items():
        missing = full_ids - set(m)
        for gid in missing:
            y, x = parse_grid_id(gid)
            a = m.get(f"{y-1}_{x}"), m.get(f"{y+1}_{x}")
            vals = [v for v in a if v is not None]
            if vals:
                m[gid] = sum(vals)/len(vals)
    return preds, weeks

def process_features(df):
    df2 = df.sort_values('week_start').drop_duplicates('grid_id', keep='last')
    return df2.set_index('grid_id').drop(['week_start','fire_occurred'], axis=1, errors='ignore').to_dict(orient='index')

# --- Initialization -----------------------------------------------------------
if not ensure_data_files():
    logger.error("Data download failed, exiting.")
    sys.exit(1)

pred_df = load_and_cache_data('predictions_v2.csv')
feat_df = load_and_cache_data('final_data.csv')
fire_df = load_and_cache_data('fire_data.csv')

predictions_by_week, available_weeks = process_predictions(pred_df)
full_feature_map = process_features(feat_df)

# --- API routes ---------------------------------------------------------------
@app.route('/', methods=['GET'])
def health(): return jsonify(status='OK')

@app.route('/api/get-weeks', methods=['GET'])
def get_weeks(): return jsonify(weeks=available_weeks)

@app.route('/api/predict', methods=['POST','OPTIONS'])
def predict():
    if request.method=='OPTIONS': return jsonify({})
    data = request.json or {}
    week = data.get('week'); bounds = data.get('bounds')
    if not week or not bounds: return jsonify(error='Invalid'),400
    gid = get_grid_id_from_bounds(bounds)
    val = predictions_by_week.get(week, {}).get(gid)
    return jsonify(prediction=(round(val,4) if val else 'No data'))

@app.route('/api/get-no-data-grids', methods=['POST','OPTIONS'])
def no_data():
    if request.method=='OPTIONS': return jsonify({})
    wk = request.json.get('week')
    all_ids = {get_grid_id_from_bounds(b) for b in generate_grid(BUTTE_BOUNDS)}
    have = set(predictions_by_week.get(wk,{}))
    return jsonify(no_data=list(all_ids-have))

@app.route('/api/get-fire-weeks', methods=['GET'])
def fire_weeks():
    weeks = fire_df[fire_df.fire_occurred==1]['week_start'].unique().tolist()
    return jsonify(fire_weeks=weeks)

@app.route('/api/predict-all', methods=['POST','OPTIONS'])
def pred_all():
    if request.method=='OPTIONS': return jsonify({})
    d=request.json or {} ; wk=d.get('week'); tiles=d.get('tiles',[])
    res=[]
    for t in tiles:
        gid=t.get('gridId') or get_grid_id_from_bounds(t.get('bounds',[]))
        p=predictions_by_week.get(wk,{}).get(gid)
        if p is not None:
            b=t['bounds']; res.append({'grid_id':gid,'center':[(b[0][0]+b[1][0])/2,(b[0][1]+b[1][1])/2],'prediction':round(p,4)})
    return jsonify(predictions=res)

@app.route('/api/get-features', methods=['POST','OPTIONS'])
def get_feats():
    if request.method=='OPTIONS': return jsonify({})
    b=request.json.get('bounds')
    gid=get_grid_id_from_bounds(b)
    return jsonify(features=full_feature_map.get(gid))

@app.after_request
def cors(resp):
    resp.headers['Access-Control-Allow-Origin']=request.headers.get('Origin','https://fire-proneness-map-frontend.onrender.com')
    resp.headers['Access-Control-Allow-Headers']='Content-Type'
    resp.headers['Access-Control-Allow-Methods']='GET,POST,OPTIONS'
    return resp

if __name__=='__main__':
    port=int(os.environ.get('PORT',5001))
    app.run(host='0.0.0.0',port=port)
