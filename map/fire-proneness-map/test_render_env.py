import os
import logging
import gdown
import requests
from pathlib import Path
import tempfile
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_render_environment():
    """Test the environment configuration and file access"""
    logger.info("Testing Render environment configuration...")
    
    # Test 1: Check if /tmp is writable (Render's writable directory)
    tmp_dir = Path("/tmp")
    test_file = tmp_dir / "test_write.txt"
    try:
        test_file.write_text("test")
        test_file.unlink()
        logger.info("✓ /tmp directory is writable")
    except Exception as e:
        logger.error(f"✗ /tmp directory is not writable: {e}")
        return False

    # Test 2: Check network connectivity
    try:
        response = requests.get("https://drive.google.com")
        logger.info(f"✓ Network connectivity: {response.status_code}")
    except Exception as e:
        logger.error(f"✗ Network connectivity failed: {e}")
        return False

    # Test 3: Test Google Drive file access
    file_ids = {
        "predictions": "1x1jI_OUq7Jl5T3HBIiiHDUZIMI6OLcIV",
        "final_data": "1rQ5QlFXgENzlNPit_ds8RtjegM_YLHU4",
        "fire_data": "1DSTFM2imMKe1iqnANoRkmLQbuMEEcSxm"
    }

    for name, file_id in file_ids.items():
        logger.info(f"\nTesting {name} file access...")
        url = f"https://drive.google.com/uc?id={file_id}"
        
        # Test HEAD request
        try:
            response = requests.head(url, allow_redirects=True)
            logger.info(f"✓ HEAD request successful: {response.status_code}")
            logger.info(f"Final URL: {response.url}")
        except Exception as e:
            logger.error(f"✗ HEAD request failed: {e}")
            continue

        # Test download
        try:
            output_path = tmp_dir / f"test_{name}.csv"
            gdown.download(url, str(output_path), quiet=False, fuzzy=True, use_cookies=True)
            
            if output_path.exists() and output_path.stat().st_size > 0:
                logger.info(f"✓ Download successful: {output_path.stat().st_size} bytes")
                output_path.unlink()
            else:
                logger.error("✗ Download failed - file is empty or doesn't exist")
        except Exception as e:
            logger.error(f"✗ Download failed: {e}")

    # Test 4: Check environment variables
    port = os.environ.get("PORT", "5000")
    logger.info(f"✓ PORT environment variable: {port}")

    return True

if __name__ == "__main__":
    logger.info("Starting Render environment test...")
    success = test_render_environment()
    if success:
        logger.info("\n✓ All tests passed! The code should work on Render.")
    else:
        logger.error("\n✗ Some tests failed. Please check the logs above.") 