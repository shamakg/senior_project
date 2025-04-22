import rasterio
from rasterio.warp import transform_bounds

# your desired WGS84 bbox
min_lon, min_lat = -122.7, 39.2
max_lon, max_lat = -121.2, 40.2

# pick one of your newly‐written files:
out_path = "processed_image_data/LC08_L2SP_044032_20131228_20200912_02_T1_SR_B4_butte.TIF"

with rasterio.open(out_path) as out:
    # bounds in the image's CRS (probably UTM)
    print("Cropped bounds in image CRS:", out.bounds)
    # reproject those bounds back to WGS84 to compare
    wgs84_bounds = transform_bounds(out.crs, "EPSG:4326",
                                    out.bounds.left, out.bounds.bottom,
                                    out.bounds.right, out.bounds.top)
    print("Cropped bounds in WGS84:", wgs84_bounds)

    print("\nDesired WGS84 bbox:")
    print((min_lon, min_lat, max_lon, max_lat))