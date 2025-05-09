import os
import re
import time
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
import numpy as np
from PIL import Image
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --------------------------------------------------------------------------------
# Configuration: Bounding box for Butte County (WGS84)
# --------------------------------------------------------------------------------
min_lon, min_lat = -122.7, 39.2
max_lon, max_lat = -121.2, 40.2

# Input and output directories
tmp_root = "image_data"
out_root = "processed_image_data"
os.makedirs(out_root, exist_ok=True)

data_bands = ('B4', 'B5', 'B10')

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
            # skip original attrdef and insert new one
            i += 1
            indent = m.group(1)
            label = m.group(2).strip()
            value = new_bounds[label]
            final.append(f"{indent}attrdef = {value};\n")
        i += 1
    os.makedirs(os.path.dirname(output_txt), exist_ok=True)
    with open(output_txt, 'w') as f:
        f.writelines(final)

# --------------------------------------------------------------------------------
# Process a single scene file (TIF and MTL)
# --------------------------------------------------------------------------------
def process_file(path):
    fname = os.path.basename(path)
    scene_id = '_'.join(fname.split('_')[:7])
    out_dir = os.path.join(out_root, scene_id)
    os.makedirs(out_dir, exist_ok=True)

    # If metadata arrives late, handle .txt here
    txt_file = os.path.join(tmp_root, f"{scene_id}_MTL.txt")
    if os.path.exists(txt_file):
        update_mtl(txt_file, os.path.join(out_dir, f"{scene_id}_MTL.txt"))
        print(f"📄 Updated MTL for {scene_id}")

    # Only process relevant bands
    if not any(b in fname for b in data_bands) and not path.lower().endswith('.tif'):
        return

    # Crop and convert TIFF -> PNG
    base, _ = os.path.splitext(fname)
    dst_png = os.path.join(out_dir, f"{base}.png")

    try:
        with rasterio.open(path) as src:
            img_bbox = transform_bounds('EPSG:4326', src.crs,
                                        min_lon, min_lat,
                                        max_lon, max_lat)
            window = from_bounds(*img_bbox, transform=src.transform)
            window = window.round_offsets().round_lengths()
            data = src.read(window=window)
    except Exception as e:
        print(f"❌ Failed to process {fname}: {e}")
        return

    # Convert first band to PNG (0-255)
    band = data[0].astype(np.float32)
    band[np.isnan(band)] = 0
    b_min, b_max = band.min(), band.max()
    if b_max > b_min:
        scaled = ((band - b_min) / (b_max - b_min) * 255).astype(np.uint8)
    else:
        scaled = np.zeros(band.shape, dtype=np.uint8)
    img = Image.fromarray(scaled)
    img.save(dst_png)
    print(f"🖼️ Converted to PNG: {scene_id}/{base}.png")

    # Remove original TIFF to save space
    try:
        os.remove(path)
        print(f"🗑️ Removed original TIFF: {fname}")
    except FileNotFoundError:
        pass

# --------------------------------------------------------------------------------
# Watchdog: Monitor for completed downloads (TIF and TXT)
# --------------------------------------------------------------------------------
class DownloadHandler(FileSystemEventHandler):
    def on_created(self, event):
        self.try_process(event)
    def on_modified(self, event):
        self.try_process(event)

    def try_process(self, event):
        if event.is_directory:
            return
        path = event.src_path
        # Handle metadata .txt arrival
        if path.lower().endswith('.txt'):
            scene_id = '_'.join(os.path.basename(path).split('_')[:7])
            out_txt = os.path.join(out_root, scene_id, os.path.basename(path))
            update_mtl(path, out_txt)
            print(f"📄 Late MTL update for {scene_id}")
            return
        # Only process TIFFs
        if not path.lower().endswith('.tif'):
            return
        # Skip incomplete downloads
        crswap = path + '.crswap'
        if os.path.exists(crswap):
            return
        try:
            size = os.path.getsize(path)
        except FileNotFoundError:
            return
        if size < 1024:
            return
        # Wait for stable file size
        prev_size = -1
        while True:
            try:
                curr = os.path.getsize(path)
            except FileNotFoundError:
                return
            if curr == prev_size:
                break
            prev_size = curr
            time.sleep(1)
        print(f"✅ Ready: {os.path.basename(path)}")
        process_file(path)

if __name__ == "__main__":
    print(f"👀 Watching '{tmp_root}' for new files...")
    observer = Observer()
    handler = DownloadHandler()
    observer.schedule(handler, tmp_root, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
