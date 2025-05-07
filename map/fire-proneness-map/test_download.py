import logging
import io
import gdown
import pandas as pd
from pathlib import Path
import requests
import time
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_file_access(file_id):
    """Test if a file is accessible via direct URL"""
    url = f"https://drive.google.com/uc?id={file_id}"
    try:
        response = requests.head(url, allow_redirects=True)
        logger.info(f"File access test for {file_id}:")
        logger.info(f"Status code: {response.status_code}")
        logger.info(f"Final URL: {response.url}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error testing file access: {e}")
        return False

def download_from_drive(file_id, output):
    """Download file from Google Drive with better error handling"""
    try:
        # First test if file is accessible
        if not test_file_access(file_id):
            logger.error(f"File {file_id} is not accessible")
            return False

        # Try direct download
        url = f"https://drive.google.com/uc?id={file_id}"
        logger.info(f"Attempting direct download from: {url}")
        
        # Download with gdown
        success = gdown.download(url, output, quiet=False)
        
        if not success:
            # If direct download fails, try with confirm token
            logger.info("Direct download failed, trying with confirm token...")
            url = f"https://drive.google.com/uc?id={file_id}&confirm=t"
            success = gdown.download(url, output, quiet=False)
            
            if not success:
                logger.error("All download attempts failed")
                return False
        
        logger.info("Download completed successfully")
        return True
            
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return False

def test_download(file_id, filename):
    """Test downloading a file from Google Drive"""
    logger.info(f"\n{'='*50}")
    logger.info(f"Testing download for {filename} (ID: {file_id})")
    logger.info(f"{'='*50}")
    
    # Test file access first
    if not test_file_access(file_id):
        logger.error(f"✗ File {filename} is not accessible")
        return False
    
    # Test downloading the file
    logger.info("Testing file download...")
    output = io.BytesIO()
    if download_from_drive(file_id, output):
        logger.info("✓ Successfully downloaded file")
        # Check if we got some data
        output.seek(0)
        content = output.read(1024)  # Read first 1KB
        if content:
            logger.info("✓ File contains data")
            # Try to read as CSV and show columns
            try:
                output.seek(0)
                df = pd.read_csv(output)
                logger.info(f"✓ Successfully parsed CSV")
                logger.info(f"File columns: {df.columns.tolist()}")
                logger.info(f"Number of rows: {len(df)}")
                logger.info(f"First few rows:\n{df.head()}")
                return True
            except Exception as e:
                logger.error(f"✗ Error reading CSV: {e}")
                return False
        else:
            logger.error("✗ Downloaded file is empty")
            return False
    else:
        logger.error("✗ Failed to download file")
        return False

def test_cache_access(cache_dir):
    """Test if cache directory is writable"""
    logger.info(f"\nTesting cache directory access...")
    try:
        cache_path = Path(cache_dir)
        cache_path.mkdir(exist_ok=True, parents=True)
        test_file = cache_path / "test.txt"
        test_file.write_text("test")
        test_file.unlink()
        logger.info("✓ Cache directory is writable")
        return True
    except Exception as e:
        logger.error(f"✗ Cache directory error: {e}")
        return False

# Test files
files = {
    "predictions": "1x1jI_OUq7Jl5T3HBIiiHDUZIMI6OLcIV",
    "final_data": "1rQ5QlFXgENzlNPit_ds8RtjegM_YLHU4",
    "fire_data": "1DSTFM2imMKe1iqnANoRkmLQbuMEEcSxm"
}

if __name__ == "__main__":
    # Test cache directory first
    if not test_cache_access("/tmp/cache"):
        logger.error("Cache directory test failed. Exiting.")
        exit(1)
    
    # Run tests
    success = True
    for name, file_id in files.items():
        if not test_download(file_id, name):
            success = False
            logger.error(f"Failed to download {name}")
        time.sleep(1)  # Add delay between tests
    
    if success:
        logger.info("\n✓ All downloads successful!")
    else:
        logger.error("\n✗ Some downloads failed. Please check the logs above.")
        exit(1) 