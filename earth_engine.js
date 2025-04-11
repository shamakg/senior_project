// Define the Area of Interest (AOI) for Butte County, California
var butteCounty = ee.Geometry.Rectangle([-122.5, 39.2, -121.3, 40.2]);

// Load the ECMWF ERA5-LAND daily aggregated dataset for 2020
var dataset = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR')
    .filterDate('2012-01-01', '2022-01-01')
    .filterBounds(butteCounty);

// Define the scale in meters (1 mile ≈ 1609.34 meters)
var scale = 1609.34;

// Function to calculate the mean for each square mile
var calculateMean = function(image) {
  return image.reduceRegions({
    collection: ee.FeatureCollection(butteCounty),
    reducer: ee.Reducer.mean(),
    scale: scale,
  });
};

// Apply the function to each image in the collection
var means = dataset.map(calculateMean);

// Flatten the list of means into a single FeatureCollection
var meansFlattened = means.flatten();

// Print the results
print(meansFlattened);

// Optionally, export the results to a CSV file
Export.table.toDrive({
  collection: meansFlattened,
  description: 'ButteCounty_Averages_Full',
  fileFormat: 'CSV'
});
