const NASA_API = "https://power.larc.nasa.gov/api/temporal/daily/point";

const locationSelect = document.getElementById("location");
const comparisonSelect = document.getElementById("comparisonLocation");
const variableSelect = document.getElementById("variable");
const startInput = document.getElementById("startYear");
const endInput = document.getElementById("endYear");
const analyzeBtn = document.getElementById("analyzeBtn");
const message = document.getElementById("message");

const MONTHS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
];

// Base complète des stations NASA POWER à travers le Maroc
const LOCATIONS = {
    fes: { name: "Fes", latitude: 34.0331, longitude: -5.0003 },
    meknes: { name: "Meknes", latitude: 33.8935, longitude: -5.5547 },
    casablanca: { name: "Casablanca", latitude: 33.5731, longitude: -7.5898 },
    rabat: { name: "Rabat", latitude: 34.0209, longitude: -6.8416 },
    mohammedia: { name: "Mohammedia", latitude: 33.6947, longitude: -7.3850 },
    marrakech: { name: "Marrakech", latitude: 31.6295, longitude: -7.9811 },
    agadir: { name: "Agadir", latitude: 30.4278, longitude: -9.5981 },
    tanger: { name: "Tangier", latitude: 35.7595, longitude: -5.8340 },
    tetouan: { name: "Tetouan", latitude: 35.5889, longitude: -5.3626 },
    oujda: { name: "Oujda", latitude: 34.6814, longitude: -1.9086 },
    taza: { name: "Taza", latitude: 34.2100, longitude: -4.0100 },
    kenitra: { name: "Kenitra", latitude: 34.2610, longitude: -6.5802 },
    safi: { name: "Safi", latitude: 32.2994, longitude: -9.2372 },
    el_jadida: { name: "El Jadida", latitude: 33.2316, longitude: -8.5007 },
    beni_mellal: { name: "Beni Mellal", latitude: 32.3394, longitude: -6.3600 },
    nador: { name: "Nador", latitude: 35.1688, longitude: -2.9335 },
    laayoune: { name: "Laayoune", latitude: 27.1536, longitude: -13.2033 },
    dakhla: { name: "Dakhla", latitude: 23.7081, longitude: -15.9338 },
    errachidia: { name: "Errachidia", latitude: 31.9316, longitude: -4.4267 },
    ouarzazate: { name: "Ouarzazate", latitude: 30.9189, longitude: -6.9370 }
};

let map;
let markers = {};

function initMap() {
    map = L.map('map', { zoomControl: true, fadeAnimation: true }).setView([32.0, -6.0], 6);

    // URL CARTO Voyager avec la clé exacte (comportant le 'l' minuscule)
    L.tileLayer('https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png?key=cb1_597l_1_f34709db55d9a33867d3df0f', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
        maxZoom: 19
    }).addTo(map);

    Object.keys(LOCATIONS).forEach(key => {
        const loc = LOCATIONS[key];
        const marker = L.marker([loc.latitude, loc.longitude]).addTo(map);
        marker.bindPopup(`<b>${loc.name}, Morocco</b><br>NASA POWER Station`);

        marker.on('click', () => {
            if (!locationSelect) return;
            for (let i = 0; i < locationSelect.options.length; i++) {
                const optVal = locationSelect.options[i].value;
                if (optVal.includes(loc.latitude.toString().slice(0, 4))) {
                    locationSelect.selectedIndex = i;
                    break;
                }
            }
            analyzeData();
        });

        markers[key] = marker;
    });

    setTimeout(() => {
        if (map) map.invalidateSize();
    }, 250);
}

function setMessage(text, type = "") {
    if (!message) return;
    message.textContent = text;
    message.className = "message " + type;
}

function setLoading(loading) {
    if (!analyzeBtn) return;
    analyzeBtn.disabled = loading;
    analyzeBtn.innerHTML = loading
        ? "◌ Processing NASA telemetry..."
        : "<span>↗</span> Analyze";
}

function updateKPIs(data) {
    if (!data) return;

    const validTemps = (data.dailyTemperatures || [])
        .map(item => item.value)
        .filter(Number.isFinite);

    const validRain = (data.dailyRain || [])
        .map(item => item.value)
        .filter(Number.isFinite);

    const averageTemperature = validTemps.length
        ? validTemps.reduce((a, b) => a + b, 0) / validTemps.length
        : null;

    const totalRain = validRain.length
        ? validRain.reduce((a, b) => a + b, 0)
        : null;

    const warmest = (data.monthly || [])
        .filter(item => item && item.temperature !== null)
        .reduce((best, item) =>
            !best || item.temperature > best.temperature
                ? item
                : best, null);

    const avgTempEl = document.getElementById("avgTemp");
    if (avgTempEl) {
        avgTempEl.innerHTML = averageTemperature === null
            ? "--"
            : `${averageTemperature.toFixed(1)} <small>°C</small>`;
    }

    const totalRainEl = document.getElementById("totalRain");
    if (totalRainEl) {
        totalRainEl.innerHTML = totalRain === null
            ? "--"
            : `${totalRain.toFixed(1)} <small>mm</small>`;
    }

    const warmestMonthEl = document.getElementById("warmestMonth");
    if (warmestMonthEl) {
        warmestMonthEl.textContent = (warmest && warmest.key)
            ? `${MONTHS[Number(warmest.key.slice(5, 7)) - 1]} ${warmest.key.slice(0, 4)}`
            : "--";
    }

    const recordCountEl = document.getElementById("recordCount");
    if (recordCountEl) {
        recordCountEl.textContent = validTemps.length.toLocaleString("en-US");
    }
}

function calculateTrend(monthlyData, isTemperature) {
    const valid = monthlyData.filter(item =>
        (isTemperature ? item.temperature : item.precipitation) !== null
    );
    if (valid.length < 2) return { slope: 0, direction: "stable" };

    let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0;
    const n = valid.length;

    valid.forEach(item => {
        const val = isTemperature ? item.temperature : item.precipitation;
        const year = parseFloat(item.key.slice(0, 4)) + (parseFloat(item.key.slice(5, 7)) - 1) / 12;
        sumX += year;
        sumY += val;
        sumXY += year * val;
        sumXX += year * year;
    });

    const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX);
    let direction = "stable";
    if (slope > 0.005) direction = "increasing (warming / rising)";
    else if (slope < -0.005) direction = "decreasing (cooling / dropping)";

    return { slope, direction };
}

function detectAnomalies(monthlyData, isTemperature) {
    const valid = monthlyData.filter(item =>
        (isTemperature ? item.temperature : item.precipitation) !== null
    );
    if (valid.length === 0) return null;

    const monthBuckets = {};
    valid.forEach(item => {
        const m = item.key.slice(5, 7);
        const val = isTemperature ? item.temperature : item.precipitation;
        if (!monthBuckets[m]) monthBuckets[m] = [];
        monthBuckets[m].push(val);
    });

    const monthMeans = {};
    for (const [m, vals] of Object.entries(monthBuckets)) {
        monthMeans[m] = vals.reduce((a, b) => a + b, 0) / vals.length;
    }

    const anomalies = valid.map(item => {
        const m = item.key.slice(5, 7);
        const val = isTemperature ? item.temperature : item.precipitation;
        const anomaly = val - monthMeans[m];
        return { key: item.key, val, anomaly };
    });

    const mostExtreme = anomalies.reduce((max, curr) =>
        Math.abs(curr.anomaly) > Math.abs(max.anomaly) ? curr : max, anomalies[0]);

    return { mostExtreme };
}

function updateAIInsights(monthlyData, isTemperature, startYear, endYear, locationName) {
    const trend = calculateTrend(monthlyData, isTemperature);
    const anomalyData = detectAnomalies(monthlyData, isTemperature);

    const unit = isTemperature ? "°C/year" : "mm/year";
    const varName = isTemperature ? "air temperature" : "precipitation";

    let anomalyText = "";
    if (anomalyData && anomalyData.mostExtreme) {
        const ext = anomalyData.mostExtreme;
        const sign = ext.anomaly > 0 ? "+" : "";
        anomalyText = ` Significant climate deviation observed in <strong>${ext.key}</strong> with a delta of <strong>${sign}${ext.anomaly.toFixed(2)} ${isTemperature ? "°C" : "mm"}</strong> from baseline.`;
    }

    const insightText = document.getElementById("insightText");
    if (insightText) {
        insightText.innerHTML = `
            Advanced telemetry analysis for <strong>${locationName}</strong> (${startYear}–${endYear}) highlights an 
            <strong>${trend.direction}</strong> pattern in ${varName}. 
            Calculated linear trend velocity: <strong>${trend.slope > 0 ? "+" : ""}${trend.slope.toFixed(4)} ${unit}</strong>.${anomalyText} 
            Processed securely via NASA POWER REST API architecture.
        `;
    }
}

function drawComparisonChart(primaryData, comparisonData, variable, primaryName, comparisonName) {
    const isTemperature = variable === "T2M";

    const tracePrimary = {
        x: primaryData.map(item => item.key),
        y: primaryData.map(item => isTemperature ? item.temperature : item.precipitation),
        type: "scatter",
        mode: "lines",
        name: primaryName,
        line: { color: isTemperature ? "#49a9ff" : "#4ce0e8", width: 2.5, shape: "spline" }
    };

    const traces = [tracePrimary];

    if (comparisonData) {
        const traceComp = {
            x: comparisonData.map(item => item.key),
            y: comparisonData.map(item => isTemperature ? item.temperature : item.precipitation),
            type: "scatter",
            mode: "lines",
            name: comparisonName,
            line: { color: "#ff8585", width: 2, dash: "dash", shape: "spline" }
        };
        traces.push(traceComp);
    }

    const layout = {
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: "DM Sans, sans-serif", color: "#91a4bd", size: 11 },
        margin: { l: 55, r: 20, t: 20, b: 55 },
        xaxis: { title: "Timeline (Monthly)", gridcolor: "#1d3048", linecolor: "#263b55", tickangle: -35, nticks: 12 },
        yaxis: { title: isTemperature ? "Temperature (°C)" : "Precipitation (mm)", gridcolor: "#1d3048", zerolinecolor: "#263b55" },
        showlegend: Boolean(comparisonData),
        legend: { x: 0, y: 1 },
        hovermode: "x unified",
        autosize: true
    };

    Plotly.react("climateChart", traces, layout, {
        responsive: true,
        displaylogo: false,
        modeBarButtonsToRemove: ["lasso2d", "select2d"]
    });

    const chartTitle = document.getElementById("chartTitle");
    const chartLocation = document.getElementById("chartLocation");
    const legendLabel = document.getElementById("legendLabel");

    if (chartTitle) chartTitle.textContent = isTemperature ? "Temperature telemetry analysis" : "Precipitation telemetry analysis";
    if (chartLocation) chartLocation.textContent = comparisonData ? `${primaryName} vs ${comparisonName}` : primaryName;
    if (legendLabel) legendLabel.textContent = isTemperature ? "Temperature" : "Precipitation";
}

function processNASAData(apiData) {
    const parameters = apiData.properties.parameter;
    const temperatures = parameters.T2M || {};
    const rain = parameters.PRECTOTCORR || {};

    const grouped = new Map();
    const dailyTemperatures = [];
    const dailyRain = [];

    for (const [date, rawValue] of Object.entries(temperatures)) {
        const value = Number(rawValue);
        if (!Number.isFinite(value) || value <= -900) continue;
        const key = `${date.slice(0, 4)}-${date.slice(4, 6)}`;
        dailyTemperatures.push({ date, value });

        if (!grouped.has(key)) {
            grouped.set(key, { temperatureSum: 0, temperatureCount: 0, precipitationSum: 0, precipitationCount: 0 });
        }
        const group = grouped.get(key);
        group.temperatureSum += value;
        group.temperatureCount++;
    }

    for (const [date, rawValue] of Object.entries(rain)) {
        const value = Number(rawValue);
        if (!Number.isFinite(value) || value <= -900) continue;
        const key = `${date.slice(0, 4)}-${date.slice(4, 6)}`;
        dailyRain.push({ date, value });

        if (!grouped.has(key)) {
            grouped.set(key, { temperatureSum: 0, temperatureCount: 0, precipitationSum: 0, precipitationCount: 0 });
        }
        const group = grouped.get(key);
        group.precipitationSum += value;
        group.precipitationCount++;
    }

    const monthly = Array.from(grouped.entries())
        .map(([key, group]) => ({
            key,
            temperature: group.temperatureCount ? group.temperatureSum / group.temperatureCount : null,
            precipitation: group.precipitationCount ? group.precipitationSum : null
        }))
        .sort((a, b) => a.key.localeCompare(b.key));

    return { monthly, dailyTemperatures, dailyRain };
}

async function fetchNASA(lat, lon, startYear, endYear) {
    const params = new URLSearchParams({
        parameters: "T2M,PRECTOTCORR",
        community: "AG",
        longitude: String(lon),
        latitude: String(lat),
        start: `${startYear}0101`,
        end: `${endYear}1231`,
        format: "JSON",
        "time-standard": "UTC"
    });
    const response = await fetch(`${NASA_API}?${params}`);
    if (!response.ok) throw new Error(`NASA API HTTP ${response.status}`);
    const apiData = await response.json();
    return processNASAData(apiData);
}

async function analyzeData() {
    if (!locationSelect || !variableSelect || !startInput || !endInput) {
        console.error("Erreur : Un ou plusieurs éléments du formulaire HTML sont introuvables.");
        return;
    }

    const variable = variableSelect.value;
    const startYear = Number(startInput.value);
    const endYear = Number(endInput.value);

    const primaryCoords = locationSelect.value.split(",");
    const primaryName = locationSelect.options[locationSelect.selectedIndex].text;

    const compVal = comparisonSelect ? comparisonSelect.value : "";
    const compName = (compVal && comparisonSelect.selectedIndex !== -1) ? comparisonSelect.options[comparisonSelect.selectedIndex].text : null;

    if (!Number.isInteger(startYear) || !Number.isInteger(endYear) || startYear < 1981 || endYear > 2026 || startYear > endYear) {
        setMessage("Please specify a valid time span between 1981 and 2026.", "error");
        return;
    }

    setLoading(true);
    setMessage("Fetching live telemetry feeds from NASA POWER servers...");

    try {
        const primaryData = await fetchNASA(Number(primaryCoords[0]), Number(primaryCoords[1]), startYear, endYear);

        let compData = null;
        if (compVal) {
            const compCoords = compVal.split(",");
            compData = (await fetchNASA(Number(compCoords[0]), Number(compCoords[1]), startYear, endYear)).monthly;
        }

        if (!primaryData.monthly.length) {
            throw new Error("Empty dataset returned from NASA telemetry nodes.");
        }

        updateKPIs(primaryData);
        drawComparisonChart(primaryData.monthly, compData, variable, primaryName, compName);
        updateAIInsights(primaryData.monthly, variable === "T2M", startYear, endYear, primaryName);

        const periodLabel = document.getElementById("periodLabel");
        if (periodLabel) periodLabel.textContent = `${startYear} — ${endYear}`;
        
        setMessage("Telemetry successfully loaded and processed via client engine.", "success");

    } catch (error) {
        console.error("NASA data fetch error:", error);
        setMessage(`Data retrieval failed: ${error.message}. Check network connection.`, "error");
    } finally {
        setLoading(false);
    }
}

// Liaison du bouton de soumission HTML
if (analyzeBtn) {
    analyzeBtn.addEventListener("click", analyzeData);
}

window.addEventListener("load", () => {
    initMap();
    analyzeData();
});