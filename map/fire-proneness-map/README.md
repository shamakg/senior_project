# Getting Started with Create React App

This project was bootstrapped with [Create React App](https://github.com/facebook/create-react-app).

## Available Scripts

In the project directory, you can run:

### `npm start`

Runs the app in the development mode.\
Open [http://localhost:3000](http://localhost:3000) to view it in your browser.

The page will reload when you make changes.\
You may also see any lint errors in the console.

### `npm test`

Launches the test runner in the interactive watch mode.\
See the section about [running tests](https://facebook.github.io/create-react-app/docs/running-tests) for more information.

### `npm run build`

Builds the app for production to the `build` folder.\
It correctly bundles React in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.\
Your app is ready to be deployed!

See the section about [deployment](https://facebook.github.io/create-react-app/docs/deployment) for more information.

### `npm run eject`

**Note: this is a one-way operation. Once you `eject`, you can't go back!**

If you aren't satisfied with the build tool and configuration choices, you can `eject` at any time. This command will remove the single build dependency from your project.

Instead, it will copy all the configuration files and the transitive dependencies (webpack, Babel, ESLint, etc) right into your project so you have full control over them. All of the commands except `eject` will still work, but they will point to the copied scripts so you can tweak them. At this point you're on your own.

You don't have to ever use `eject`. The curated feature set is suitable for small and middle deployments, and you shouldn't feel obligated to use this feature. However we understand that this tool wouldn't be useful if you couldn't customize it when you are ready for it.

## Learn More

You can learn more in the [Create React App documentation](https://facebook.github.io/create-react-app/docs/getting-started).

To learn React, check out the [React documentation](https://reactjs.org/).

### Code Splitting

This section has moved here: [https://facebook.github.io/create-react-app/docs/code-splitting](https://facebook.github.io/create-react-app/docs/code-splitting)

### Analyzing the Bundle Size

This section has moved here: [https://facebook.github.io/create-react-app/docs/analyzing-the-bundle-size](https://facebook.github.io/create-react-app/docs/analyzing-the-bundle-size)

### Making a Progressive Web App

This section has moved here: [https://facebook.github.io/create-react-app/docs/making-a-progressive-web-app](https://facebook.github.io/create-react-app/docs/making-a-progressive-web-app)

### Advanced Configuration

This section has moved here: [https://facebook.github.io/create-react-app/docs/advanced-configuration](https://facebook.github.io/create-react-app/docs/advanced-configuration)

### Deployment

This section has moved here: [https://facebook.github.io/create-react-app/docs/deployment](https://facebook.github.io/create-react-app/docs/deployment)

### `npm run build` fails to minify

This section has moved here: [https://facebook.github.io/create-react-app/docs/troubleshooting#npm-run-build-fails-to-minify](https://facebook.github.io/create-react-app/docs/troubleshooting#npm-run-build-fails-to-minify)

# Fire Proneness Map Backend

This is the backend server for the Fire Proneness Map application. It provides API endpoints for accessing fire prediction data and related features.

## Data Requirements

The server requires three data files to function:

1. `predictions_v2.csv` - Contains fire prediction data
2. `final_data.csv` - Contains feature data for each grid cell
3. `fire_data.csv` - Contains historical fire occurrence data

These files are not included in the repository due to their size. They are hosted as GitHub Releases and will be downloaded automatically when the server starts.

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Run the server:

```bash
python server.py
```

The server will automatically download any missing data files on startup.

## API Endpoints

- `GET /api/get-weeks` - Get list of available weeks
- `POST /api/predict` - Get prediction for a specific location and week
- `POST /api/get-no-data-grids` - Get list of grid cells without data
- `GET /api/get-fire-weeks` - Get list of weeks with fire occurrences
- `POST /api/predict-all` - Get predictions for multiple locations
- `POST /api/get-features` - Get features for a specific location

## Development

For local development, you can run the server with:

```bash
PORT=5001 python server.py
```

The server will use port 5001 by default in development mode.

## Deployment

The server is configured to run on Render. It will automatically download the required data files during deployment.

## Data Files

The data files are hosted as GitHub Releases and will be downloaded automatically. If you need to update the data files:

1. Create a new release on GitHub
2. Upload the new data files to the release
3. Update the release version in the `DATA_FILES` configuration in `server.py`
4. Deploy the updated code

## Caching

The server uses Parquet files for caching the data. The cache files are stored in the same directory as the data files and are automatically created when the data is first loaded.
