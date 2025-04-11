import geopandas as gpd
from shapely.geometry import Point
import pandas as pd

pd.set_option('display.max_columns', None)  # show all columns
pd.set_option('display.width', 1000) 

county_shp = "/Users/sumesh/Library/Mobile Documents/com~apple~CloudDocs/Desktop/Senior Project/ca_counties"  # Update with actual file path
counties = gpd.read_file(county_shp)



# Filter for Butte County
butte_boundary = counties[counties['NAME'] == 'Butte']

# Save as GeoJSON
geojson_path = "/Users/sumesh/Library/Mobile Documents/com~apple~CloudDocs/Desktop/Senior Project/butte_county.geojson"
butte_boundary.to_file(geojson_path, driver="GeoJSON")

# print(butte_boundary)

polygon = butte_boundary.geometry.iloc[0]  # Assuming there's only one Butte County polygon

# Print the polygon itself (WKT format)
print(polygon)

# Print the list of exterior coordinates (only outer boundary)
print(list(polygon.exterior.coords))
print(butte_boundary['geometry'])
