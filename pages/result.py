import os

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

from utils.charts import build_price_3d_chart, build_market_map


load_dotenv()


API_BASE = os.environ.get(
    "FARMORA_API_BASE",
    "http://127.0.0.1:8000"
).rstrip("/")


# ============================================================
# GET PREDICTION DATA
# ============================================================

prediction = st.session_state.get(
    "prediction"
)


if not prediction:

    st.warning(
        "No prediction details found."
    )

    if st.button(
        "Back to Prediction",
        type="primary"
    ):

        st.switch_page(
            "pages/predict.py"
        )

    st.stop()


state = prediction[
    "state"
]

district = prediction[
    "district"
]

crop = prediction[
    "crop"
]

production_cost = float(
    prediction[
        "production_cost"
    ]
)

arrival_date = prediction.get(
    "arrival_date"
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="glass-card">
        <h1>📊 Farmora Results</h1>
        <p>
            Crop price analysis with historical observations and future forecasts.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# SELECTED DETAILS
# ============================================================

st.write(
    "### Prediction Details"
)


c1, c2, c3, c4 = st.columns(4)


c1.metric(
    "State",
    state
)

c2.metric(
    "District",
    district
)

c3.metric(
    "Crop",
    crop
)

c4.metric(
    "Production Cost",
    f"₹{production_cost:,.0f}/qtl"
)


# ============================================================
# FETCH PRICE DATA
# ============================================================

with st.spinner(
    "Fetching AGMARKNET price data..."
):

    try:

        response = requests.post(

            f"{API_BASE}/price-history",

            json={

                "state":
                    state,

                "district":
                    district,

                "crop":
                    crop,

                "arrival_date":
                    arrival_date,

                "forecast_months":
                    12
            },

            timeout=180
        )

    except requests.exceptions.RequestException as exc:

        st.error(
            "Couldn't reach the FastAPI backend."
        )

        st.code(
            str(exc)
        )

        st.stop()


if response.status_code != 200:

    try:

        detail = response.json().get(
            "detail",
            response.text
        )

    except Exception:

        detail = response.text

    st.error(
        f"Prediction failed: {detail}"
    )

    st.stop()


price_data = response.json()


# ============================================================
# CURRENT PRICE
# ============================================================

latest = price_data.get(
    "latest"
)


if latest:

    st.write(
        "### 💰 Current Mandi Price"
    )

    m1, m2, m3 = st.columns(3)

    def _fmt(value):
        try:
            return f"{float(value):,.0f}"
        except (TypeError, ValueError):
            return "N/A"

    m1.metric("Min Price (₹/qtl)", _fmt(latest.get("min_price")))
    m2.metric("Modal Price (₹/qtl)", _fmt(latest.get("modal_price")))
    m3.metric("Max Price (₹/qtl)", _fmt(latest.get("max_price")))

    st.caption(
        f"Market: {latest['market']} • "
        f"Date: {latest['date']}"
    )


# ============================================================
# HISTORICAL DATE RESULT
# ============================================================

if arrival_date:

    st.write(
        f"### 📅 Prices on {arrival_date}"
    )

    selected_records = price_data.get(
        "selected_date_records",
        []
    )

    if selected_records:

        date_df = pd.DataFrame(
            selected_records
        )

        display_columns = [

            "market",

            "variety",

            "grade",

            "arrival_date",

            "min_price",

            "modal_price",

            "max_price"
        ]

        available = [
            column
            for column in display_columns
            if column in date_df.columns
        ]

        st.dataframe(
            date_df[available],
            width="stretch",
            hide_index=True
        )

    else:

        latest_date = latest["date"] if latest else None
        st.info(
            "No mandi reported a price for this crop in this district on the selected date "
            "(markets don't report every day, and today's prices appear only after the mandi "
            "uploads them). "
            + (f"The most recent available price is from {latest_date}." if latest_date else "")
        )


# ============================================================
# PAST, PRESENT AND FUTURE PRICE LINE GRAPH
# ============================================================

st.write("### 📈 Past, Present & Future Price")

history = pd.DataFrame(price_data.get("monthly_history", []))
forecast = pd.DataFrame(price_data.get("forecast", []))

for frame in (history, forecast):
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame.get("date"), errors="coerce")
        frame["modal_price"] = pd.to_numeric(frame.get("modal_price"), errors="coerce")
        frame.dropna(subset=["date", "modal_price"], inplace=True)

present_point = None
if latest and latest.get("date") and latest.get("modal_price") is not None:
    present_date = pd.to_datetime(latest.get("date"), errors="coerce")
    present_price = pd.to_numeric(latest.get("modal_price"), errors="coerce")
    if pd.notna(present_date) and pd.notna(present_price):
        present_point = {"date": present_date, "modal_price": float(present_price)}

chart = build_price_3d_chart(history, present_point, forecast)

if chart is not None:
    st.plotly_chart(chart, width="stretch")
    st.caption(
        "Blue = past monthly average modal prices, amber = latest observed (present) price, "
        "green = forecast. "
        "Forecast values are statistical estimates, not guaranteed market prices."
    )
else:
    st.info("No historical or forecast price series is available for this selection.")


# ============================================================
# MARKET LOCATIONS (keep locations; do not display coordinates)
# ============================================================

st.write("### 🗺️ Mandi Locations")
st.caption("All mandi markets reporting prices in the selected district.")

locations = []
with st.spinner("Locating mandi markets (the first lookup for a district can take a minute)..."):
    try:
        map_response = requests.post(
            f"{API_BASE}/market-locations",
            json={"state": state, "district": district, "crop": crop},
            timeout=300,
        )
        if map_response.status_code == 200:
            locations = map_response.json().get("locations", [])
        else:
            st.info("Market locations are temporarily unavailable for this selection.")
    except requests.exceptions.RequestException:
        st.info("Could not connect to the market-location service. Price results remain available.")

if locations:
    locations_df = pd.DataFrame(locations)

    # Normalize coordinate field names for map rendering only.
    if "latitude" in locations_df.columns and "lat" not in locations_df.columns:
        locations_df.rename(columns={"latitude": "lat"}, inplace=True)
    if "longitude" in locations_df.columns and "lon" not in locations_df.columns:
        locations_df.rename(columns={"longitude": "lon"}, inplace=True)

    # Coordinates are used internally for the map but are never shown in a table.
    if "lat" in locations_df.columns and "lon" in locations_df.columns:
        locations_df["lat"] = pd.to_numeric(locations_df["lat"], errors="coerce")
        locations_df["lon"] = pd.to_numeric(locations_df["lon"], errors="coerce")
        valid_map = locations_df.dropna(subset=["lat", "lon"])
        if not valid_map.empty:
            st.pydeck_chart(build_market_map(valid_map), height=480)
            st.caption(
                f"{len(valid_map)} mandi markets in {district}. "
                "Hover over a red dot to see the market name."
            )
        else:
            st.info("Location coordinates were not available for these markets.")
    else:
        st.info("Location coordinates were not available for these markets.")
else:
    st.info("No mandi locations were found for this selection.")


# ============================================================
# PROFIT / LOSS
# ============================================================

if (
    not forecast.empty
    and production_cost > 0
):

    predicted_average = float(
        forecast[
            "modal_price"
        ].mean()
    )

    predicted_final = float(
        forecast[
            "modal_price"
        ].iloc[-1]
    )

    average_difference = (
        predicted_average
        - production_cost
    )

    final_difference = (
        predicted_final
        - production_cost
    )

    st.write(
        "### 💵 Estimated Profit / Loss"
    )

    p1, p2, p3 = st.columns(3)

    p1.metric(
        "Production Cost",
        f"₹{production_cost:,.0f}/qtl"
    )

    p2.metric(
        "Average Forecast Price",
        f"₹{predicted_average:,.0f}/qtl"
    )

    p3.metric(
        "Estimated Difference",
        f"₹{average_difference:,.0f}/qtl"
    )

    if average_difference >= 0:

        st.success(
            f"Estimated average margin: "
            f"₹{average_difference:,.2f}/qtl"
        )

    else:

        st.warning(
            f"Estimated average loss: "
            f"₹{abs(average_difference):,.2f}/qtl"
        )

    st.caption(
        f"Final forecast difference: "
        f"₹{final_difference:,.2f}/qtl"
    )


# ============================================================
# SUGGESTIONS PAGE LINK
# ============================================================

st.write("### 🌱 Crop Suggestions")
st.caption("Open a separate page to review market-based crop suggestions for this district.")
if st.button("View Crop Suggestions →", type="primary", width="stretch"):
    st.switch_page("pages/suggestions.py")


# ============================================================
# BACK
# ============================================================

st.write("")


if st.button(
    "← Back to Prediction",
    width="stretch"
):

    st.switch_page(
        "pages/predict.py"
    )