import os
import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds
import xml.etree.ElementTree as ET
import re

# Define Butte County bounding box (lat/lon)
BUTTE_BOUNDS_LATLON = {
    "west": -122.5,
    "south": 39.3,
    "east": -121.2,
    "north": 40.2,
}

def parse_met_file(met_path):
    """Extracts start date from .met file."""
    with open(met_path, 'r') as f:
        content = f.read()
    match = re.search(r"begdate\s*=\s*(\d{4}-\d{2}-\d{2})", content)
    return match.group(1) if match else None

def crop_and_rename_first_image(data_root):
    # Get the first folder in the directory
    folders = [f for f in os.listdir(data_root) if os.path.isdir(os.path.join(data_root, f))]
    if not folders:
        print("No folders found.")
        return

    folder = folders[0]
    folder_path = os.path.join(data_root, folder)

    # Locate the .tif and .met files
    tif_file = next((f for f in os.listdir(folder_path) if f.lower().endswith(".tif")), None)
    met_file = next((f for f in os.listdir(folder_path) if f.lower().endswith(".met")), None)

    if not tif_file or not met_file:
        print("Missing .tif or .met file.")
        return

    tif_path = os.path.join(folder_path, tif_file)
    met_path = os.path.join(folder_path, met_file)

    # Get date from metadata
    date_str = parse_met_file(met_path)
    if not date_str:
        print("Could not find date in .met file.")
        return

    # Crop using rasterio
    with rasterio.open(tif_path) as src:
        # Transform Butte bounds to image CRS
        bounds_img_crs = transform_bounds("EPSG:4326", src.crs, 
                                          BUTTE_BOUNDS_LATLON["west"],
                                          BUTTE_BOUNDS_LATLON["south"],
                                          BUTTE_BOUNDS_LATLON["east"],
                                          BUTTE_BOUNDS_LATLON["north"])
        # Define crop window
        window = from_bounds(*bounds_img_crs, transform=src.transform)
        window = window.round_offsets().round_lengths()

        # Read the window
        cropped = src.read(window=window)
        out_transform = src.window_transform(window)

        # Output path
        out_path = os.path.join(folder_path, f"{date_str}.tif")

        # Save cropped image
        profile = src.profile
        profile.update({
            "height": cropped.shape[1],
            "width": cropped.shape[2],
            "transform": out_transform
        })

        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(cropped)

    print(f"Cropped and saved: {out_path}")

    # Optionally, remove the original large file
    os.remove(tif_path)
    print(f"Removed original image: {tif_path}")

def crop_folder(folder_path):
    """Crop the NDVI image in a specific folder using its .met file."""
    import rasterio
    from rasterio.warp import transform_bounds
    from rasterio.windows import from_bounds

    # Locate the .tif and .met files
    tif_file = next((f for f in os.listdir(folder_path) if f.lower().endswith(".tif")), None)
    met_file = next((f for f in os.listdir(folder_path) if f.lower().endswith(".met")), None)

    if not tif_file or not met_file:
        print(f"Missing .tif or .met file in {folder_path}")
        return

    tif_path = os.path.join(folder_path, tif_file)
    met_path = os.path.join(folder_path, met_file)

    # Get date from metadata
    date_str = parse_met_file(met_path)
    if not date_str:
        print(f"Could not find date in .met file in {folder_path}")
        return

    # Crop using rasterio
    with rasterio.open(tif_path) as src:
        # Transform Butte bounds to image CRS
        bounds_img_crs = transform_bounds("EPSG:4326", src.crs, 
                                          BUTTE_BOUNDS_LATLON["west"],
                                          BUTTE_BOUNDS_LATLON["south"],
                                          BUTTE_BOUNDS_LATLON["east"],
                                          BUTTE_BOUNDS_LATLON["north"])
        # Define crop window
        window = from_bounds(*bounds_img_crs, transform=src.transform)
        window = window.round_offsets().round_lengths()

        # Read the window
        cropped = src.read(window=window)
        out_transform = src.window_transform(window)

        # Output path
        out_path = os.path.join(folder_path, f"{date_str}.tif")

        # Save cropped image
        profile = src.profile
        profile.update({
            "height": cropped.shape[1],
            "width": cropped.shape[2],
            "transform": out_transform
        })

        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(cropped)

    print(f"Cropped and saved: {out_path}")

    # Optionally remove the original .tif
    os.remove(tif_path)
    print(f"Removed original image: {tif_path}")


def crop_all_images(data_root):
    """Crop NDVI image in every folder inside the given root."""
    folders = [f for f in os.listdir(data_root) if os.path.isdir(os.path.join(data_root, f))]
    for folder in folders:
        folder_path = os.path.join(data_root, folder)
        try:
            crop_folder(folder_path)
        except Exception as e:
            print(f"Error processing {folder_path}: {e}")

crop_all_images("processed_image_data")