import os
import zipfile
import shutil

def is_ndvi_tif(filename):
    """
    Determines if a file is an NDVI .tif file.
    Excludes files containing 'VI_QUAL' in their names.
    """
    return filename.lower().endswith('.tif') and 'vi_ndvi' in filename.lower() and 'vi_qual' not in filename.lower()

def extract_ndvi_from_zip(zip_path, extract_to):
    """
    Extracts NDVI .tif files from a ZIP archive to a specified directory.
    Deletes non-NDVI files after extraction.
    """
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        # List of NDVI .tif files to extract
        ndvi_files = [f for f in zip_ref.namelist() if is_ndvi_tif(f)]
        
        if not ndvi_files:
            print(f"No NDVI .tif files found in {zip_path}.")
            return
        
        # Create a subdirectory for the extracted files (name it after the zip file)
        zip_name = os.path.splitext(os.path.basename(zip_path))[0]
        extract_path = os.path.join(extract_to, zip_name)
        os.makedirs(extract_path, exist_ok=True)
        
        # Extract NDVI .tif files
        for file in ndvi_files:
            zip_ref.extract(file, path=extract_path)
            print(f"Extracted {file} to {extract_path}")
        
        # Optionally, extract and store metadata if present
        metadata_files = [f for f in zip_ref.namelist() if f.lower().endswith('.met')]
        for meta_file in metadata_files:
            zip_ref.extract(meta_file, path=extract_path)
            print(f"Extracted metadata {meta_file} to {extract_path}")
        
        # Delete non-NDVI files from the extracted directory
        for root, dirs, files in os.walk(extract_path):
            for file in files:
                file_path = os.path.join(root, file)
                if not is_ndvi_tif(file) and not file.lower().endswith('.met'):
                    os.remove(file_path)
                    print(f"Deleted non-NDVI file {file_path}")
        
        # Remove the original ZIP folder if empty
        for root, dirs, files in os.walk(extract_path, topdown=False):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)
                    print(f"Removed empty folder {dir_path}")

def process_all_zips(zip_folder, output_folder):
    """
    Processes all ZIP files in the specified folder.
    """
    for item in os.listdir(zip_folder):
        if item.lower().endswith('.zip'):
            zip_path = os.path.join(zip_folder, item)
            extract_ndvi_from_zip(zip_path, output_folder)
            # Remove the original zip file to save space
            os.remove(zip_path)
            print(f"Removed original ZIP file: {zip_path}")

# Set the folder paths
zip_folder_path = 'image_data'  # Folder where the ZIP files are located
output_folder_path = 'processed_image_data'  # Folder where the processed files will be saved

# Process the ZIP files and extract NDVI data
process_all_zips(zip_folder_path, output_folder_path)
