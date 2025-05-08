import requests
import psutil
import time
import json

def get_memory_usage():
    process = psutil.Process()
    return process.memory_info().rss / 1024 / 1024  # Convert to MB

def test_api():
    base_url = "http://localhost:10000"
    
    # Test 1: Get available weeks
    print("\nTest 1: Getting available weeks")
    print(f"Memory before: {get_memory_usage():.2f} MB")
    response = requests.get(f"{base_url}/api/get-weeks")
    print(f"Response: {response.json()}")
    print(f"Memory after: {get_memory_usage():.2f} MB")
    
    # Test 2: Get predictions for a specific week
    print("\nTest 2: Getting predictions")
    print(f"Memory before: {get_memory_usage():.2f} MB")
    test_bounds = [[39.2, -122.6], [39.3, -122.5]]
    response = requests.post(
        f"{base_url}/api/predict",
        json={"week": "2020-01-01", "bounds": test_bounds}
    )
    print(f"Response: {response.json()}")
    print(f"Memory after: {get_memory_usage():.2f} MB")
    
    # Test 3: Get features
    print("\nTest 3: Getting features")
    print(f"Memory before: {get_memory_usage():.2f} MB")
    response = requests.post(
        f"{base_url}/api/get-features",
        json={"bounds": test_bounds}
    )
    print(f"Response: {response.json()}")
    print(f"Memory after: {get_memory_usage():.2f} MB")
    
    # Test 4: Get fire weeks
    print("\nTest 4: Getting fire weeks")
    print(f"Memory before: {get_memory_usage():.2f} MB")
    response = requests.get(f"{base_url}/api/get-fire-weeks")
    print(f"Response: {response.json()}")
    print(f"Memory after: {get_memory_usage():.2f} MB")

if __name__ == "__main__":
    print("Starting memory usage test...")
    print(f"Initial memory usage: {get_memory_usage():.2f} MB")
    
    try:
        test_api()
    except Exception as e:
        print(f"Error during testing: {e}")
    
    print(f"\nFinal memory usage: {get_memory_usage():.2f} MB") 