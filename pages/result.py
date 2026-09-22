import os

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()


API_BASE = os.environ.get(
    "FARMORA_API_BASE",
    "http://127.0.0.1:8000"
).rstrip("/")


# ============================================================
# Get prediction data
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


state = prediction["state"]
district = prediction["district"]
crop = prediction["crop"]
production_cost = float(
    prediction["production_cost"]
)


# ============================================================
# Header
# ============================================================

st.markdown(
    """
    <div class="glass-card">
        <h1>📊 Farmora Results</h1>
        <p>
            Crop price analysis, future forecast,
            market locations and crop suggestions.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# Selected Details
# ============================================================

st.write("### Prediction Details")

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
# Fetch price prediction
# ============================================================

with st.spinner(
    "Fetching AGMARKNET price data and generating forecast..."
):

    try:

        response = requests.post(
            f"{API_BASE}/price-history",
            json={
                "state": state,
                "district": district,
                "crop": crop,
                "forecast_months": 12
            },
            timeout=120
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
# Current Price
# ============================================================

latest = price_data.get(
    "latest"
)


if latest:

    st.write(
        "### 💰 Current Mandi Price"
    )

    m1, m2, m3 = st.columns(3)

    m1.metric(
        "Min Price (₹/qtl)",
        f"{latest['min_price']:,.0f}"
    )

    m2.metric(
        "Modal Price (₹/qtl)",
        f"{latest['modal_price']:,.0f}"
    )

    m3.metric(
        "Max Price (₹/qtl)",
        f"{latest['max_price']:,.0f}"
    )

    st.caption(
        f"Market: {latest['market']} • "
        f"Date: {latest['date']}"
    )


# ============================================================
# Historical Price Graph
# ============================================================

st.write(
    "### 📈 Historical Crop Prices"
)


history = pd.DataFrame(
    price_data.get(
        "monthly_history",
        []
    )
)


if not history.empty:

    history["date"] = pd.to_datetime(
        history["date"]
    )

    history = (
        history
        .set_index("date")
        [["modal_price"]]
        .rename(
            columns={
                "modal_price":
                "Modal Price (₹/qtl)"
            }
        )
    )

    st.line_chart(
        history,
        use_container_width=True
    )

else:

    st.info(
        "No historical monthly price data available."
    )


# ============================================================
# Future Forecast
# ============================================================

st.write(
    "### 🔮 Next 12-Month Price Forecast"
)


forecast = pd.DataFrame(
    price_data.get(
        "forecast",
        []
    )
)


if forecast.empty:

    st.warning(
        "Not enough data to generate a future forecast."
    )

else:

    forecast["date"] = pd.to_datetime(
        forecast["date"]
    )

    forecast_chart = forecast.set_index(
        "date"
    )[["modal_price"]].rename(
        columns={
            "modal_price":
            "Predicted Price (₹/qtl)"
        }
    )

    st.line_chart(
        forecast_chart,
        use_container_width=True
    )

    st.caption(
        "Forecast is generated from historical AGMARKNET "
        "price patterns using machine learning. "
        "It is an estimated value, not a guaranteed market price."
    )


# ============================================================
# Past + Future Combined
# ============================================================

if not history.empty and not forecast.empty:

    st.write(
        "### 📊 Past, Present & Future Price Trend"
    )

    past_for_chart = history.reset_index()

    past_for_chart = past_for_chart.rename(
        columns={
            "Modal Price (₹/qtl)": "Price"
        }
    )

    future_for_chart = forecast[
        ["date", "modal_price"]
    ].copy()

    future_for_chart = future_for_chart.rename(
        columns={
            "modal_price": "Price"
        }
    )

    combined = pd.concat(
        [
            past_for_chart[
                ["date", "Price"]
            ],
            future_for_chart[
                ["date", "Price"]
            ]
        ],
        ignore_index=True
    )

    combined = (
        combined
        .drop_duplicates("date")
        .sort_values("date")
        .set_index("date")
    )

    st.line_chart(
        combined,
        use_container_width=True
    )


# ============================================================
# Estimated Profit / Loss
# ============================================================

if not forecast.empty and production_cost > 0:

    predicted_average = float(
        forecast["modal_price"].mean()
    )

    predicted_final = float(
        forecast["modal_price"].iloc[-1]
    )

    average_profit = (
        predicted_average
        - production_cost
    )

    final_profit = (
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
        f"₹{average_profit:,.0f}/qtl"
    )

    if average_profit >= 0:

        st.success(
            f"Estimated average margin: "
            f"₹{average_profit:,.2f}/qtl"
        )

    else:

        st.warning(
            f"Estimated average loss: "
            f"₹{abs(average_profit):,.2f}/qtl"
        )


# ============================================================
# Mandi Locations
# ============================================================

st.write(
    "### 🗺️ Mandi Locations"
)


with st.spinner(
    "Locating mandi markets..."
):

    try:

        map_response = requests.post(
            f"{API_BASE}/market-locations",
            json={
                "state": state,
                "district": district,
                "crop": crop
            },
            timeout=120
        )

        if map_response.status_code == 200:

            locations = (
                map_response
                .json()
                .get("locations", [])
            )

        else:

            locations = []

    except requests.exceptions.RequestException:

        locations = []


if locations:

    map_df = pd.DataFrame(
        locations
    )

    st.map(
        map_df[["lat", "lon"]]
    )

    st.dataframe(
        map_df[
            ["market", "lat", "lon"]
        ],
        use_container_width=True,
        hide_index=True
    )

else:

    st.info(
        "Couldn't locate mandi coordinates "
        "for this selection."
    )


# ============================================================
# Crop Suggestions
# ============================================================

st.write(
    "### 🌾 Next-Year Crop Suggestions"
)


with st.spinner(
    "Analyzing local market demand..."
):

    try:

        suggestion_response = requests.post(
            f"{API_BASE}/crop-suggestions",
            json={
                "state": state,
                "district": district,
                "selected_crop": crop
            },
            timeout=120
        )

        if suggestion_response.status_code == 200:

            suggestions = (
                suggestion_response
                .json()
                .get("suggestions", [])
            )

        else:

            suggestions = []

    except requests.exceptions.RequestException:

        suggestions = []


if suggestions:

    suggestion_df = pd.DataFrame(
        suggestions
    )

    display_columns = [
        "crop",
        "average_price",
        "market_count",
        "trend_percent"
    ]

    available_columns = [
        column
        for column in display_columns
        if column in suggestion_df.columns
    ]

    st.dataframe(
        suggestion_df[
            available_columns
        ],
        use_container_width=True,
        hide_index=True
    )

    st.caption(
        "Suggestions are based on crop availability, "
        "market activity, recent price levels and "
        "recent price trends in the selected district."
    )

else:

    st.info(
        "No crop suggestion data was available "
        "for this district."
    )


# ============================================================
# Back
# ============================================================

st.write("")

if st.button(
    "← Back to Prediction",
    use_container_width=True
):

    st.switch_page(
        "pages/predict.py"
    )