# 🌾 Farmora — Smart Crop Price & Suggestion System

Farmora helps Indian farmers make better selling and planting decisions from real mandi (market) price data. Pick a state, district and crop, enter your production cost, and Farmora shows today's mandi prices, past price trends, a 12‑month price estimate, an estimated profit/loss per quintal, a map of the district's mandis, and other crops showing strong market activity.

> **Disclaimer:** forecasts are statistical estimates built from sparse public data. They are not guaranteed prices or agronomic/financial advice.

---

## Features

| Feature | Description |
|---|---|
| **Current mandi price** | Latest min / modal / max price (₹ per quintal) from AGMARKNET |
| **Historical date lookup** | Optional: prices on a chosen arrival date, per market, variety and grade |
| **Past · Present · Future chart** | Stacked column chart: past monthly averages (blue), latest observed price (amber), 12‑month forecast (green) |
| **Profit / loss estimate** | Average forecast price compared with your production cost |
| **Mandi map** | Every mandi reporting in the district as a red dot; hover for the market name (pydeck) |
| **Crop suggestions** | Other crops in the district ranked by market activity, price and trend |
| **Offline resilience** | API responses are cached on disk and used if the government API is down |

---

## Workflow

```
 ┌────────────┐   state, district, crop,    ┌──────────────────┐
 │ Predict    │   production cost, date     │ Streamlit        │
 │ page       │ ─────────────────────────▶  │ session_state    │
 └────────────┘                             └────────┬─────────┘
                                                     ▼
 ┌────────────┐  POST /price-history        ┌──────────────────┐   HTTPS    ┌───────────────┐
 │ Result     │ ─────────────────────────▶  │ FastAPI backend  │ ─────────▶ │ data.gov.in   │
 │ page       │  POST /market-locations     │ (backend/main.py)│            │ AGMARKNET API │
 │            │ ◀─────────────────────────  │                  │ ─────────▶ │ OpenStreetMap │
 └─────┬──────┘   JSON                      └──────────────────┘            │ Nominatim     │
       │                                                                    └───────────────┘
       └─▶ Suggestions page ──▶ POST /crop-suggestions
```

1. **Predict** – the user fills the form; values are stored in `st.session_state`.
2. **Result** – calls the backend, which fetches records from AGMARKNET (live daily dataset + historical archive), cleans them, builds monthly averages and a forecast.
3. **Map** – market names are geocoded with OpenStreetMap Nominatim (cached in `data/geocode_cache.json`) and plotted with pydeck.
4. **Suggestions** – all crops reporting in the district are scored and ranked.

### How the forecast works
Observed modal prices are averaged per month. The most recent 12 months are fitted with a straight line; the slope is capped at ±15 % of the last price and **damped** (×0.8 each month) so the estimate does not run away. With fewer than 3 months of data the last price is repeated. There is no trained machine‑learning model — this is a transparent baseline, and accuracy depends heavily on how much data the API returns.

### How crop suggestions are scored
For each crop in the last 12 months of data: `score = 0.30·observations + 0.25·(markets·5) + 0.25·(avg price/100) + 0.20·trend%` (each term capped). It is a market‑activity indicator, not a recommendation of what to grow.

---

## Project structure

```
farmora/
├── app.py                     # Streamlit entry: page config, CSS, navigation
├── pages/
│   ├── home.py                # Landing page
│   ├── predict.py             # Input form
│   ├── result.py              # Prices, chart, map, profit/loss
│   ├── suggestions.py         # Crop suggestions
│   ├── help.py                # How-to and troubleshooting
│   └── about.py               # Project information
├── backend/
│   ├── main.py                # FastAPI app and endpoints
│   └── services/
│       ├── agmarknet.py       # API client, caching, cleaning, monthly history
│       ├── forecasting.py     # Damped linear price forecast
│       ├── geocoding.py       # Market name → lat/lon (Nominatim + cache)
│       └── recommendations.py # Crop scoring
├── utils/
│   ├── crops.py               # Crop list + AGMARKNET name aliases
│   └── charts.py              # Stacked price chart + pydeck map
├── assets/cornfield.jpg       # Background image
├── data/                      # Runtime caches (git-ignored)
├── requirements.txt
├── runtime.txt                # Python 3.11.9
├── .env.example
└── LICENSE
```

---

## Tech stack

- **Language:** Python 3.11.9
- **Frontend:** Streamlit, Plotly (charts), pydeck (map)
- **Backend:** FastAPI, Uvicorn
- **Data:** pandas, NumPy
- **Data sources:** AGMARKNET via [data.gov.in](https://data.gov.in) (daily mandi prices), OpenStreetMap Nominatim (geocoding), countriesnow.space (state/district lists)

---

## Setup

### 1. Prerequisites
- Python **3.11.9**
- A free API key from [data.gov.in](https://data.gov.in) (register → *My Account* → API key)

### 2. Install
```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate        macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure
Copy `.env.example` to `.env` and fill it in:
```
AGMARKNET_API_KEY=your_data_gov_in_api_key
FARMORA_API_BASE=http://127.0.0.1:8000
# optional: override the live-price dataset id
# AGMARKNET_RESOURCE_ID=9ef84268-d588-465a-a308-a864a43d0070
```

### 4. Run (two terminals, from the project root)
```bash
# Terminal 1 – backend
uvicorn backend.main:app --port 8000

# Terminal 2 – frontend
streamlit run app.py
```
Open http://localhost:8501.

---

## API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Service check |
| POST | `/price-history` | Latest price, selected-date records, monthly history, 12‑month forecast |
| POST | `/market-locations` | Mandi names with coordinates for the map |
| POST | `/crop-suggestions` | Ranked crops for a district |

Interactive docs: http://127.0.0.1:8000/docs

---

## Troubleshooting

| Problem | Fix |
|---|---|
| "Couldn't reach the FastAPI backend" | Start the backend (step 4) and check `FARMORA_API_BASE` |
| "AGMARKNET_API_KEY is missing" | Create `.env` from `.env.example` |
| "No price data found" | That crop may not be traded in the district, or the name differs in AGMARKNET; try another crop or district |
| No record for the selected date | Mandis do not report every day; the latest available date is shown instead |
| Map is slow the first time | Nominatim allows 1 request/second; results are cached afterwards |
| `visibility` TypeError at start | Upgrade Streamlit: `pip install -U "streamlit>=1.56"` |

---

## Limitations
- Public API responses may be capped per request, so data can be sparse for some districts/crops.
- Forecasts are a simple trend baseline with no seasonality or weather input.
- Market locations come from name search and may be missing or approximate for small mandis.

## License
Released under the [MIT License](LICENSE).
