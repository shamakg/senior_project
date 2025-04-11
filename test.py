import pandas as pd
import matplotlib.pyplot as plt
from shapely.geometry import shape
import geopandas as gpd

file_path = "combined_ButteCounty_Averages_NEW.parquet"

pd.set_option('display.max_rows', None) 
pd.set_option('display.max_columns', None) 
pd.set_option('display.width', None) 
pd.set_option('display.max_colwidth', None)  



df = pd.read_parquet(file_path, engine='pyarrow')


print("Columns:", df.head())
print("Data Types:\n", df.dtypes)
print(df[['dewpoint_temperature_2m', 'evaporation_from_bare_soil_sum', 'temperature_2m',".geo", "system:index"]].iloc[0:10])

features = ["temperature_2m", "leaf_area_index_low_vegetation_min", "total_precipitation_sum", ".geo"]

first_geo = df['.geo'].iloc[0]
second_geo = df['.geo'].iloc[1]


first_polygon = shape(eval(first_geo))
second_polygon = shape(eval(second_geo))


fig, ax = plt.subplots(figsize=(8, 8))


x1, y1 = first_polygon.exterior.xy
ax.fill(x1, y1, alpha=0.5, fc='blue', label="First Polygon")


x2, y2 = second_polygon.exterior.xy
ax.fill(x2, y2, alpha=0.5, fc='green', label="Second Polygon")


ax.set_title("First and Second Polygons of the First Two Data Points")
ax.set_xlabel("Longitude")
ax.set_ylabel("Latitude")
ax.legend()
ax.grid(True)


plt.show()