# 🌍 EarthTrend AI — Planetary Climate Intelligence

**EarthTrend AI** is an interactive climate analytics dashboard developed for the **NASA Space Apps Challenge**. It empowers researchers, students, and citizens to visualize historical climate data, compare regional trends, and detect environmental anomalies using real-time NASA Earth observation datasets.

## 🚀 Key Features
* **Real-Time NASA POWER Integration:** Direct asynchronous fetching of daily Air Temperature (`T2M`) and Corrected Precipitation (`PRECTOTCORR`) records from 1981 to 2026.
* **Geospatial Station Explorer:** Interactive **Leaflet.js** map allowing users to select meteorological monitoring points across Morocco (Mohammedia, Casablanca, Rabat, Fès, Meknès, Marrakech, Agadir).
* **Multi-City Comparative Analytics:** Side-by-side historical curve rendering powered by **Plotly.js** to contrast coastal vs. continental climate patterns.
* **Automated AI & Statistical Insights:** Real-time computation of linear regression slopes (°C/year or mm/year) and automated isolation of extreme monthly climate anomalies relative to historical baselines.

## 🛠️ Tech Stack
* **Frontend:** HTML5, CSS3 (Custom Space/Futurism UI), Vanilla JavaScript (ES6+)
* **Data Visualization:** Plotly.js
* **Geospatial Mapping:** Leaflet.js & OpenStreetMap
* **Data Source:** NASA Langley Research Center (LaRC) POWER Project API

## 💻 How to Run Locally
1. Clone this repository:
   ```bash
   git clone [https://github.com/honnybaddger019/nasa-trend-detective.git](https://github.com/honnybaddger019/nasa-trend-detective.git)