import logging
import io
import gdown
import pandas as pd
from pathlib import Path
import shutil
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_temp_files():
    """Clean up any temporary files created by gdown"""
    try:
        # Clean up gdown's temporary directory if it exists
        gdown_tmp = Path('/tmp/gdown')
        if gdown_tmp.exists():
            shutil.rmtree(gdown_tmp)
            logger.info("Cleaned up gdown temporary files")
    except Exception as e:
        logger.error(f"Error cleaning up temporary files: {e}")

def download_from_drive(file_id, output):
    """Download file from Google Drive with better error handling"""
    try:
        # Use gdown with direct download URL
        url = f"https://drive.google.com/uc?id={file_id}"
        gdown.download(url, output, quiet=False)
        logger.info("Download completed successfully")
        
        # Clean up any temporary files
        cleanup_temp_files()
        return True
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        cleanup_temp_files()
        return False

def test_download(file_id, filename):
    """Test downloading a file from Google Drive"""
    logger.info(f"\nTesting download for {filename}...")
    
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
                logger.info(f"File columns: {df.columns.tolist()}")
                logger.info(f"First few rows:\n{df.head()}")
                # Clear memory
                del df
                return True
            except Exception as e:
                logger.error(f"Error reading CSV: {e}")
            finally:
                # Clear memory
                output.close()
                del output
        else:
            logger.error("✗ Downloaded file is empty")
            return False
    else:
        logger.error("✗ Failed to download file")
        return False

# Test files
files = {
    "predictions": "1x1jI_OUq7Jl5T3HBIiiHDUZIMI6OLcIV",
    "final_data": "1rQ5QlFXgENzlNPit_ds8RtjegM_YLHU4",
    "fire_data": "1DSTFM2imMKe1iqnANoRkmLQbuMEEcSxm"
}

# Run tests
success = True
for name, file_id in files.items():
    if not test_download(file_id, name):
        success = False
        logger.error(f"Failed to download {name}")
    logger.info("-" * 50)

if success:
    logger.info("All downloads successful!")
else:
    logger.error("Some downloads failed. Please check the logs above.")

# Final cleanup
cleanup_temp_files() 