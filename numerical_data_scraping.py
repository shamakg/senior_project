import pandas as pd
import geopandas as gpd
from shapely.geometry import shape
from geopy.distance import geodesic

# Load the dataset
df = pd.read_csv('ButteCounty_Averages_Full.csv')

# Function to extract coordinates from the geo column
def extract_coordinates(geo_string):
    geo_dict = eval(geo_string)  # Convert the string to a dictionary
    coordinates = geo_dict['coordinates'][0]  # Extract coordinates from the polygon
    return coordinates

# Add a new column with extracted coordinates
df['coordinates'] = df['.geo'].apply(extract_coordinates)

print(df['coordinates'])

def calculate_distance(coord1, coord2):
    # Swap coordinates to match the expected format [latitude, longitude]
    coord1 = (coord1[1], coord1[0])  # [latitude, longitude]
    coord2 = (coord2[1], coord2[0])  # [latitude, longitude]
    
    return geodesic(coord1, coord2).miles

# List to store distances
distances = []

# Loop through the dataset and calculate distance between consecutive points
for i in range(1, len(df)):
    prev_coords = df.loc[i-1, 'coordinates'][0]  # First coordinate in previous row
    curr_coords = df.loc[i, 'coordinates'][0]  # First coordinate in current row
    distance = calculate_distance(prev_coords, curr_coords)
    distances.append(distance)

# Add the distance between points to the dataframe
df['distance_to_previous'] = [None] + distances

# Check the first few rows to see the result
print(df[['system:index', 'distance_to_previous']].head())
