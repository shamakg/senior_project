import os
import re
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
import numpy as np
from PIL import Image

# --------------------------------------------------------------------------------
# Configuration: Bounding box for Butte County (WGS84)
# --------------------------------------------------------------------------------
min_lon, min_lat = -122.7, 39.2
max_lon, max_lat = -121.2, 40.2

# Input and output directories
tmp_root = "image_data"
out_root = "processed_image_data"
os.makedirs(out_root, exist_ok=True)

# --------------------------------------------------------------------------------
# Helper: Update MTL (.txt) with new bounding coordinates
# --------------------------------------------------------------------------------
def update_mtl(input_txt, output_txt):
    with open(input_txt, 'r') as f:
        lines = f.readlines()

    new_bounds = {
        'Upper Left Latitude':   max_lat,
        'Upper Left Longitude':  min_lon,
        'Upper Right Latitude':  max_lat,
        'Upper Right Longitude': max_lon,
        'Lower Right Latitude':  min_lat,
        'Lower Right Longitude': max_lon,
        'Lower Left Latitude':   min_lat,
        'Lower Left Longitude':  min_lon
    }

    final = []
    i = 0
    while i < len(lines):
        line = lines[i]
        final.append(line)
        m = re.match(r"(\s*)attrlabl\s*=\s*(.+?);", line)
        if m and m.group(2).strip() in new_bounds:
            i += 1
            indent = m.group(1)
            label = m.group(2).strip()
            value = new_bounds[label]
            final.append(f"{indent}attrdef = {value};\n")
        i += 1

    with open(output_txt, 'w') as f:
        f.writelines(final)

# --------------------------------------------------------------------------------
# Group files by scene
# --------------------------------------------------------------------------------
scenes = {}
for fname in os.listdir(tmp_root):
    if not fname.lower().endswith(('.tif', '.txt')):
        continue
    scene_key = '_'.join(fname.split('_')[:7])
    scenes.setdefault(scene_key, []).append(fname)

data_bands = ('B4', 'B5', 'B10')

# --------------------------------------------------------------------------------
# Process scenes
# --------------------------------------------------------------------------------
for scene_id, files in scenes.items():
    out_dir = os.path.join(out_root, scene_id)
    os.makedirs(out_dir, exist_ok=True)

    for fname in files:
        src_path = os.path.join(tmp_root, fname)

        # Copy and update MTL
        if fname.lower().endswith('.txt'):
            dst_txt = os.path.join(out_dir, fname)
            update_mtl(src_path, dst_txt)
            print(f"📝 Updated MTL for scene {scene_id}")
            continue

        # Only process specific bands
        if not any(b in fname for b in data_bands):
            continue

        # PNG output
        base, _ = os.path.splitext(fname)
        dst_png = os.path.join(out_dir, f"{base}.png")

        try:
            with rasterio.open(src_path) as src:
                img_bbox = transform_bounds('EPSG:4326', src.crs,
                                            min_lon, min_lat,
                                            max_lon, max_lat)
                window = from_bounds(*img_bbox, transform=src.transform)
                window = window.round_offsets().round_lengths()
                data = src.read(window=window)
        except rasterio.errors.RasterioIOError as e:
            print(f"⚠️ Skipping unreadable file: {fname} — {e}")
            continue

        # Convert first band to PNG
        band = data[0].astype(np.float32)
        band[np.isnan(band)] = 0
        b_min, b_max = band.min(), band.max()
        if b_max > b_min:
            scaled = ((band - b_min) / (b_max - b_min) * 255).astype(np.uint8)
        else:
            scaled = np.zeros(band.shape, dtype=np.uint8)

        img = Image.fromarray(scaled)
        img.save(dst_png)
        print(f"🖼️  Converted to PNG: {scene_id}/{base}.png")

# --------------------------------------------------------------------------------
# Optional Cleanup: Delete everything in image_data once processed
# --------------------------------------------------------------------------------
for fname in os.listdir(tmp_root):
    path = os.path.join(tmp_root, fname)
    try:
        os.remove(path)
        print(f"🧹 Deleted: {fname}")
    except Exception as e:
        print(f"⚠️ Could not delete {fname}: {e}")
