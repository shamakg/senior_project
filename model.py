import numpy as np
import tensorflow as tf
from tensorflow.keras import layers, models
import matplotlib.pyplot as plt

# Step 1: Generate Synthetic Data
def generate_synthetic_data(num_samples=1000, img_size=(64, 64)):
    """Generates synthetic satellite images and numerical data."""
    images = np.random.rand(num_samples, img_size[0], img_size[1], 3)  # RGB satellite images
    numerical_data = np.random.rand(num_samples, 3)  # Temp, Humidity, Power Line Proximity
    labels = np.random.randint(0, 2, size=(num_samples, 1))  # Fire occurrence (0 or 1)
    return images, numerical_data, labels

# Generate data
images, numerical_data, labels = generate_synthetic_data()

# Step 2: Define CNN for Image Feature Extraction
def build_cnn_model(input_shape):
    """Defines a CNN model for extracting image features."""
    model = models.Sequential([
        layers.Conv2D(32, (3, 3), activation='relu', input_shape=input_shape),
        layers.MaxPooling2D((2, 2)),
        layers.Conv2D(64, (3, 3), activation='relu'),
        layers.MaxPooling2D((2, 2)),
        layers.Conv2D(128, (3, 3), activation='relu'),
        layers.Flatten(),
        layers.Dense(128, activation='relu')
    ])
    return model

# Step 3: Define LSTM for Temporal Analysis
def build_lstm_model():
    """Defines an LSTM model for temporal fire risk analysis."""
    model = models.Sequential([
        layers.LSTM(64, return_sequences=True, input_shape=(5, 3)),
        layers.LSTM(32, return_sequences=False),
        layers.Dense(16, activation='relu')
    ])
    return model

# Step 4: Combine CNN and LSTM
def build_hybrid_model(image_shape, numerical_shape):
    """Combines CNN and LSTM models for fire prediction."""
    cnn = build_cnn_model(image_shape)
    lstm = build_lstm_model()
    
    img_input = layers.Input(shape=image_shape)
    num_input = layers.Input(shape=(5, numerical_shape))  # 5 time steps of numerical data
    
    img_features = cnn(img_input)
    num_features = lstm(num_input)
    
    merged = layers.concatenate([img_features, num_features])
    output = layers.Dense(1, activation='sigmoid')(merged)
    
    model = models.Model(inputs=[img_input, num_input], outputs=output)
    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
    
    return model

# Define Model
image_shape = (64, 64, 3)
numerical_shape = 3
model = build_hybrid_model(image_shape, numerical_shape)

# Print Model Summary
model.summary()
