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

def test_file_download(file_id, name, tmp_dir):
    """Test downloading a specific file with multiple URL formats"""
    # Create a persistent session
    session = requests.Session()
    
    urls = [
        f"https://drive.google.com/uc?id={file_id}",  # Standard format
        f"https://drive.google.com/file/d/{file_id}/view",  # File view format
        f"https://drive.google.com/uc?export=download&id={file_id}"  # Export format
    ]
    
    for url in urls:
        logger.info(f"\nTesting {name} file access with URL: {url}")
        
        # Test HEAD request
        try:
            response = session.head(url, allow_redirects=True)
            logger.info(f"✓ HEAD request successful: {response.status_code}")
            logger.info(f"Final URL: {response.url}")
            
            if response.status_code != 200:
                logger.warning(f"URL returned status {response.status_code}, trying next URL")
                continue
                
            # If we get a virus scan warning, try to get the confirm token
            if 'confirm=' in response.url:
                confirm_token = response.url.split('confirm=')[1].split('&')[0]
                url = f"{url}&confirm={confirm_token}"
                logger.info(f"Using confirm token: {confirm_token}")
                
        except Exception as e:
            logger.warning(f"HEAD request failed: {e}")
            continue

        # Test download
        try:
            output_path = tmp_dir / f"test_{name}.csv"
            gdown.download(url, str(output_path), quiet=False, fuzzy=True, use_cookies=True)
            
            if output_path.exists() and output_path.stat().st_size > 0:
                # Verify file content is not HTML
                with open(output_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(1024)
                    if '<!DOCTYPE html>' in content or '<html>' in content:
                        logger.warning("Downloaded content is HTML, trying next URL")
                        output_path.unlink()
                        continue
                
                logger.info(f"✓ Download successful: {output_path.stat().st_size} bytes")
                output_path.unlink()
                return True
            else:
                logger.warning("Download failed - file is empty or doesn't exist")
                if output_path.exists():
                    output_path.unlink()
        except Exception as e:
            logger.warning(f"Download failed: {e}")
            if output_path.exists():
                output_path.unlink()
    
    logger.error(f"All download attempts failed for {name}")
    return False

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

    all_downloads_successful = True
    for name, file_id in file_ids.items():
        if not test_file_download(file_id, name, tmp_dir):
            all_downloads_successful = False

    # Test 4: Check environment variables
    port = os.environ.get("PORT", "5000")
    logger.info(f"✓ PORT environment variable: {port}")

    return all_downloads_successful

if __name__ == "__main__":
    logger.info("Starting Render environment test...")
    success = test_render_environment()
    if success:
        logger.info("\n✓ All tests passed! The code should work on Render.")
    else:
        logger.error("\n✗ Some tests failed. Please check the logs above.") 