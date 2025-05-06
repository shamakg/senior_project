const express = require("express");
const cors = require("cors");
const bodyParser = require("body-parser");
const tf = require("@tensorflow/tfjs-node");
const fs = require("fs");
const path = require("path");
const csv = require("csv-parser");

const app = express();
const port = 5000;

app.use(cors());
app.use(bodyParser.json());

let model;
let latestDataByGrid = {}; // grid_id -> features array

// Load model and data at startup
async function loadModelAndData() {
  console.log("Loading model...");
  model = await tf.loadLayersModel("file://my_model.h5/model.json"); // Make sure `model.json` is present
  console.log("Model loaded.");

  console.log("Loading data...");
  const dataRows = [];
  fs.createReadStream("final2021_data.csv")
    .pipe(csv())
    .on("data", (row) => {
      dataRows.push(row);
    })
    .on("end", () => {
      console.log(`Loaded ${dataRows.length} rows.`);

      // Find latest date
      dataRows.sort((a, b) => new Date(b.date) - new Date(a.date));
      const latestDate = dataRows[0].date;
      const latestRows = dataRows.filter((r) => r.date === latestDate);

      latestRows.forEach((row) => {
        const gridId = row.grid_id;
        delete row.grid_id;
        delete row.date;

        const featureValues = Object.values(row).map((v) => parseFloat(v));
        latestDataByGrid[gridId] = featureValues;
      });

      console.log(`Prepared ${Object.keys(latestDataByGrid).length} grid feature rows.`);
    });
}

app.post("/api/predict", async (req, res) => {
  const { bounds } = req.body;
  if (!bounds || bounds.length !== 2) {
    return res.status(400).json({ error: "Invalid bounds" });
  }

  try {
    // Find the closest matching grid_id
    const centerLat = (bounds[0][0] + bounds[1][0]) / 2;
    const centerLng = (bounds[0][1] + bounds[1][1]) / 2;
    const gridId = `${centerLat.toFixed(4)}_${centerLng.toFixed(4)}`;

    const features = latestDataByGrid[gridId];
    if (!features) {
      return res.json({ prediction: "No data for this grid." });
    }

    const inputTensor = tf.tensor2d([features]);
    const prediction = model.predict(inputTensor);
    const output = (await prediction.data())[0];

    res.json({ prediction: output > 0.5 ? "High Risk" : "Low Risk" });
  } catch (err) {
    console.error("Error predicting:", err);
    res.status(500).json({ error: "Model prediction failed." });
  }
});

app.listen(port, async () => {
  await loadModelAndData();
  console.log(`Server running at http://localhost:${port}`);
});
