import pandas as pd
import geopandas as gpd

# Environmental grid bounds
grid_origin_lon = -122.5
grid_origin_lat = 39.2
chunk_size = 0.015
max_grid_x = 79
max_grid_y = 66

min_lon = grid_origin_lon
max_lon = grid_origin_lon + chunk_size * max_grid_x
min_lat = grid_origin_lat
max_lat = grid_origin_lat + chunk_size * max_grid_y


shp_path = "/Users/sumesh/Library/Mobile Documents/com~apple~CloudDocs/Desktop/Senior Project/mtbs_perimeter_data"
gdf = gpd.read_file(shp_path)

gdf_proj = gdf.to_crs(epsg=32610)


gdf_proj['centroid'] = gdf_proj.geometry.centroid


gdf_proj = gdf_proj.set_geometry('centroid').to_crs(epsg=4326)


gdf_proj['centroid_lon'] = gdf_proj.geometry.x
gdf_proj['centroid_lat'] = gdf_proj.geometry.y


gdf_filtered = gdf_proj[
    (gdf_proj['centroid_lon'] >= min_lon) & (gdf_proj['centroid_lon'] <= max_lon) &
    (gdf_proj['centroid_lat'] >= min_lat) & (gdf_proj['centroid_lat'] <= max_lat)
]


gdf_filtered.to_csv("/Users/sumesh/Library/Mobile Documents/com~apple~CloudDocs/Desktop/Senior Project/butte_fires_NEW.csv", index=False)
