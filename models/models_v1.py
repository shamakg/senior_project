import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from sklearn.preprocessing import MinMaxScaler
from sklearn.model_selection import train_test_split
import matplotlib.pyplot as plt


env_data = pd.read_csv("ButteCounty_Averages_Full.csv")
fire_data = pd.read_csv("butte_fires.csv")


env_data['date'] = pd.to_datetime(env_data['system:index'].str[:8], format='%Y%m%d')
fire_data['date'] = pd.to_datetime(fire_data['Ig_Date'])  

fire_data = fire_data[['date', 'BurnBndAc']]
env_data.drop(columns=['system:index', '.geo'], inplace=True, errors='ignore')


fire_data["BurnBndAc"] = fire_data["BurnBndAc"].fillna(0)


data = pd.merge(env_data, fire_data[['date', 'BurnBndAc']], on='date', how='left')


data['BurnBndAc'].fillna(0, inplace=True)


features = ["temperature_2m", "leaf_area_index_low_vegetation_min", "total_precipitation_sum"]



scaler = MinMaxScaler()
data_scaled = scaler.fit_transform(data[features])


def create_sequences(data, seq_length):
    X, y = [], []
    for i in range(len(data) - seq_length):
        X.append(data[i:i+seq_length])
        y.append(data[i+seq_length][-1])  
    return np.array(X), np.array(y)


seq_length = 30 


X, y = create_sequences(data_scaled, seq_length)


X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)


model = Sequential([
    LSTM(50, activation='relu', return_sequences=True, input_shape=(seq_length, X.shape[2])),
    Dropout(0.2),
    LSTM(50, activation='relu'),
    Dropout(0.2),
    Dense(1)  # Predicting burned area
])


model.compile(optimizer='adam', loss='mse', metrics=['mae'])


history = model.fit(X_train, y_train, epochs=50, batch_size=16, validation_data=(X_test, y_test))


plt.plot(history.history['loss'], label='Train Loss')
plt.plot(history.history['val_loss'], label='Validation Loss')
plt.legend()
plt.show()


y_pred = model.predict(X_test)


y_pred_inv = scaler.inverse_transform(np.column_stack([np.zeros((len(y_pred), len(features)-1)), y_pred]))[:, -1]
y_test_inv = scaler.inverse_transform(np.column_stack([np.zeros((len(y_test), len(features)-1)), y_test]))[:, -1]


plt.plot(y_test_inv, label='Actual Burned Area')
plt.plot(y_pred_inv, label='Predicted Burned Area', linestyle='dashed')
plt.legend()
plt.show()


model.save("wildfire_lstm_model.h5")
