import pandas as pd
import matplotlib.pyplot as plt
from shapely.geometry import shape
import geopandas as gpd

file_path = "combined_ButteCounty_Averages_NEW.parquet"

pd.set_option('display.max_rows', None)  # Set to None to display all rows
pd.set_option('display.max_columns', None)  # Set to None to display all columns
pd.set_option('display.width', None)  # Automatically adjust width for better readability
pd.set_option('display.max_colwidth', None)  # Set column width to None for full content


# Read only a small portion
df = pd.read_parquet(file_path, engine='pyarrow')

# Display metadata
print("Columns:", df.head())
print("Data Types:\n", df.dtypes)
print(df[['dewpoint_temperature_2m', 'evaporation_from_bare_soil_sum', 'temperature_2m',".geo", "system:index"]].iloc[0:10])

features = ["temperature_2m", "leaf_area_index_low_vegetation_min", "total_precipitation_sum", ".geo"]

first_geo = df['.geo'].iloc[0]
second_geo = df['.geo'].iloc[1]

# Convert the .geo columns (GeoJSON-like strings) to Shapely geometry objects
first_polygon = shape(eval(first_geo))
second_polygon = shape(eval(second_geo))

# Plot the first and second polygons using Matplotlib
fig, ax = plt.subplots(figsize=(8, 8))

# Plot the first polygon
x1, y1 = first_polygon.exterior.xy
ax.fill(x1, y1, alpha=0.5, fc='blue', label="First Polygon")

# Plot the second polygon
x2, y2 = second_polygon.exterior.xy
ax.fill(x2, y2, alpha=0.5, fc='green', label="Second Polygon")

# Add titles and labels
ax.set_title("First and Second Polygons of the First Two Data Points")
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
ax.legend()
ax.grid(True)

# Show the plot
plt.show()