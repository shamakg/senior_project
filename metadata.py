import rasterio

def get_tiff_metadata(file_path):
    with rasterio.open(file_path) as dataset:
        # Check for general metadata
        metadata = dataset.tags()
        print("Metadata:", metadata)

        # You can check specific metadata tags for dates here, e.g., acquisition date
        if 'DATE_ACQUIRED' in metadata:
            print("Acquisition Date:", metadata['DATE_ACQUIRED'])

# Example usage
get_tiff_metadata('processed_image_data/US_eMAH_NDVI.2012.003-009.1KM.VI_NDVI.006.2017073070412.tif')