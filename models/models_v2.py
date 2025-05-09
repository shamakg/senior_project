import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight
import matplotlib.pyplot as plt


env_data = pd.read_parquet("combined_ButteCounty_Averages_NEW.parquet", engine='pyarrow')
fire_data = pd.read_csv("butte_fires_NEW.csv")


env_data['date'] = pd.to_datetime(env_data['week_start'])
fire_data['date'] = pd.to_datetime(fire_data['Ig_Date'])


env_data = env_data[env_data['date'] >= pd.to_datetime("2012-01-01")]
fire_data = fire_data[fire_data['date'] >= pd.to_datetime("2012-01-01")]


fire_data = fire_data[['date', 'BurnBndAc', 'BurnBndLat', 'BurnBndLon']].copy()
fire_data['BurnBndAc'] = fire_data['BurnBndAc'].fillna(0)


grid_origin_lon = -122.5
grid_origin_lat = 39.2
chunk_size = 0.015  # 0.015 grid size


fire_data['grid_x'] = ((fire_data['BurnBndLon'] - grid_origin_lon) / chunk_size).apply(np.floor).astype(int)
fire_data['grid_y'] = ((fire_data['BurnBndLat'] - grid_origin_lat) / chunk_size).apply(np.floor).astype(int)


def get_affected_cells(row):
    affected = []
    center_x = int(np.floor((row['BurnBndLon'] - grid_origin_lon) / chunk_size))
    center_y = int(np.floor((row['BurnBndLat'] - grid_origin_lat) / chunk_size))
    radius = int(np.ceil(np.sqrt(row['BurnBndAc']) / np.sqrt(640)))  # Approximate radius of burn area
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            affected.append((row['date'], center_x + dx, center_y + dy))
    return affected

overlay_fire_data = fire_data.apply(get_affected_cells, axis=1).explode().dropna()
overlay_fire_data = pd.DataFrame(overlay_fire_data.tolist(), columns=['date', 'grid_x', 'grid_y'])
overlay_fire_data['fire_occurred'] = 1
fire_occurrence = overlay_fire_data.drop_duplicates().reset_index(drop=True)


fire_occurrence['grid_x'] = fire_occurrence['grid_x'].astype(int)
fire_occurrence['grid_y'] = fire_occurrence['grid_y'].astype(int)


env_data['grid_x'] = ((env_data['grid_x'] - grid_origin_lon) / chunk_size).apply(np.floor).astype(int) 
env_data['grid_y'] = ((env_data['grid_y'] - grid_origin_lat) / chunk_size).apply(np.floor).astype(int)


min_lat = grid_origin_lat
max_lat = grid_origin_lat + chunk_size * env_data['grid_y'].max()
min_lon = grid_origin_lon
max_lon = grid_origin_lon + chunk_size * env_data['grid_x'].max()

fire_data = fire_data[
    (fire_data['BurnBndLat'] >= min_lat) &
    (fire_data['BurnBndLat'] <= max_lat) &
    (fire_data['BurnBndLon'] >= min_lon) &
    (fire_data['BurnBndLon'] <= max_lon)
]


data = pd.merge(env_data, fire_occurrence[['date', 'grid_x', 'grid_y', 'fire_occurred']], on=['date', 'grid_x', 'grid_y'], how='left')

data['fire_occurred'] = data['fire_occurred'].fillna(0)


percentages = data['fire_occurred'].value_counts(normalize=True) * 100
print("Fire Occurrence Distribution (%):")
print(percentages)


features = [
    "dewpoint_temperature_2m",
    "evaporation_from_bare_soil_sum",
    "volumetric_soil_water_layer_2",
    "temperature_2m",
    "total_precipitation_sum",
    "leaf_area_index_low_vegetation_min"
]

scaler = MinMaxScaler()
data_scaled = scaler.fit_transform(data[features])


def create_sequences(data, seq_length, forecast_horizon):
    X, y = [], []
    for i in range(len(data) - seq_length - forecast_horizon):
        X.append(data[i:i+seq_length])
        y.append(data[i+seq_length+forecast_horizon][-1]) 
    return np.array(X), np.array(y)

seq_length = 30
forecast_horizon = 29  
X, y = create_sequences(data_scaled, seq_length, forecast_horizon)


X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)


class_weights = compute_class_weight('balanced', classes=np.unique(y_train), y=y_train)
class_weight_dict = dict(zip(np.unique(y_train), class_weights))


import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout

model = Sequential([
    LSTM(50, activation='relu', return_sequences=True, input_shape=(seq_length, X.shape[2])),
    Dropout(0.2),
    LSTM(50, activation='relu'),
    Dropout(0.2),
    Dense(1, activation='sigmoid')  # Binary classification for fire occurrence
])

model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])


history = model.fit(X_train, y_train, epochs=5, batch_size=16, validation_data=(X_test, y_test), class_weight=class_weight_dict)


plt.plot(history.history['loss'], label='Train Loss')
plt.plot(history.history['val_loss'], label='Validation Loss')
plt.legend()
plt.show()


model.save("wildfire_lstm_model.h5")


def plot_fire_grid():
    plt.figure(figsize=(10, 8))
    plt.scatter(fire_occurrence['grid_x'], fire_occurrence['grid_y'], c='red', label='Fire Occurrence', alpha=0.6)
    plt.xlabel("Grid X (Longitude-based)")
    plt.ylabel("Grid Y (Latitude-based)")
    plt.title("Fire Occurrences Mapped to Grid Cells")
    plt.legend()
    plt.show()

plot_fire_grid()
