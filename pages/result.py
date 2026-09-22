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
            Crop price analysis, future forecast,
            market locations and crop suggestions.
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

        st.info(
            "No AGMARKNET price record was found "
            "for this crop on the selected arrival date."
        )


# ============================================================
# HISTORICAL PRICE GRAPH
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
        history["date"],
        errors="coerce"
    )

    history["modal_price"] = pd.to_numeric(
        history["modal_price"],
        errors="coerce"
    )

    history = history.dropna(
        subset=[
            "date",
            "modal_price"
        ]
    )

    history_chart = (
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
        history_chart,
        width="stretch"
    )

else:

    st.info(
        "No historical monthly price data available."
    )


# ============================================================
# FUTURE FORECAST
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
        "Not enough historical data to generate "
        "a future forecast."
    )

else:

    forecast["date"] = pd.to_datetime(
        forecast["date"],
        errors="coerce"
    )

    forecast["modal_price"] = pd.to_numeric(
        forecast["modal_price"],
        errors="coerce"
    )

    forecast = forecast.dropna(
        subset=[
            "date",
            "modal_price"
        ]
    )

    forecast_chart = (
        forecast
        .set_index("date")
        [["modal_price"]]
        .rename(
            columns={
                "modal_price":
                    "Predicted Price (₹/qtl)"
            }
        )
    )

    st.line_chart(
        forecast_chart,
        width="stretch"
    )

    st.caption(
        "Forecast values are estimates generated "
        "from historical AGMARKNET price patterns "
        "using machine learning/statistical forecasting. "
        "They are not guaranteed market prices."
    )


# ============================================================
# PAST + FUTURE
# ============================================================

if (
    not history.empty
    and not forecast.empty
):

    st.write(
        "### 📊 Past, Present & Future Price Trend"
    )

    past = history[
        [
            "date",
            "modal_price"
        ]
    ].copy()

    past.rename(
        columns={
            "modal_price":
                "Price"
        },
        inplace=True
    )

    future = forecast[
        [
            "date",
            "modal_price"
        ]
    ].copy()

    future.rename(
        columns={
            "modal_price":
                "Price"
        },
        inplace=True
    )

    combined = pd.concat(
        [
            past,
            future
        ],
        ignore_index=True
    )

    combined = (
        combined
        .drop_duplicates(
            "date"
        )
        .sort_values(
            "date"
        )
        .set_index(
            "date"
        )
    )

    st.line_chart(
        combined,
        width="stretch"
    )


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
# MARKET LOCATIONS
# ============================================================

st.write(
    "### 🗺️ Mandi Locations"
)


locations = []


with st.spinner(
    "Locating mandi markets..."
):

    try:

        map_response = requests.post(

            f"{API_BASE}/market-locations",

            json={

                "state":
                    state,

                "district":
                    district,

                "crop":
                    crop
            },

            timeout=180
        )

        if map_response.status_code == 200:

            locations = (
                map_response
                .json()
                .get(
                    "locations",
                    []
                )
            )

        else:

            try:

                error_detail = (
                    map_response
                    .json()
                    .get(
                        "detail",
                        map_response.text
                    )
                )

            except Exception:

                error_detail = (
                    map_response.text
                )

            st.warning(
                f"Could not load market locations: "
                f"{error_detail}"
            )

    except requests.exceptions.RequestException as exc:

        st.warning(
            "Could not connect to the market "
            "location service."
        )

        st.caption(
            str(exc)
        )


# ============================================================
# SAFE MAP HANDLING
# ============================================================

if locations:

    map_df = pd.DataFrame(
        locations
    )

    # --------------------------------------------------------
    # Handle possible backend field names
    # --------------------------------------------------------

    if (
        "latitude" in map_df.columns
        and "lat" not in map_df.columns
    ):

        map_df.rename(
            columns={
                "latitude":
                    "lat"
            },
            inplace=True
        )

    if (
        "longitude" in map_df.columns
        and "lon" not in map_df.columns
    ):

        map_df.rename(
            columns={
                "longitude":
                    "lon"
            },
            inplace=True
        )

    # --------------------------------------------------------
    # Verify coordinates
    # --------------------------------------------------------

    if (
        "lat" in map_df.columns
        and "lon" in map_df.columns
    ):

        map_df["lat"] = pd.to_numeric(
            map_df["lat"],
            errors="coerce"
        )

        map_df["lon"] = pd.to_numeric(
            map_df["lon"],
            errors="coerce"
        )

        map_df = map_df.dropna(
            subset=[
                "lat",
                "lon"
            ]
        )

        if not map_df.empty:

            st.map(
                map_df[
                    ["lat", "lon"]
                ],
                width="stretch"
            )

            table_columns = [
                column
                for column in [
                    "market",
                    "lat",
                    "lon"
                ]
                if column in map_df.columns
            ]

            if table_columns:

                st.dataframe(
                    map_df[
                        table_columns
                    ],
                    width="stretch",
                    hide_index=True
                )

        else:

            st.info(
                "Market names were found, but "
                "valid coordinates could not be obtained."
            )

    else:

        st.info(
            "Market locations were returned, "
            "but latitude/longitude data is unavailable."
        )

else:

    st.info(
        "Couldn't locate mandi coordinates "
        "for this selection."
    )


# ============================================================
# CROP SUGGESTIONS
# ============================================================

st.write(
    "### 🌾 Next-Year Crop Suggestions"
)


suggestions = []


with st.spinner(
    "Analyzing local market activity..."
):

    try:

        suggestion_response = requests.post(

            f"{API_BASE}/crop-suggestions",

            json={

                "state":
                    state,

                "district":
                    district,

                "selected_crop":
                    crop
            },

            timeout=180
        )

        if suggestion_response.status_code == 200:

            suggestions = (
                suggestion_response
                .json()
                .get(
                    "suggestions",
                    []
                )
            )

        else:

            try:

                error_detail = (
                    suggestion_response
                    .json()
                    .get(
                        "detail",
                        suggestion_response.text
                    )
                )

            except Exception:

                error_detail = (
                    suggestion_response.text
                )

            st.warning(
                f"Could not generate crop suggestions: "
                f"{error_detail}"
            )

    except requests.exceptions.RequestException as exc:

        st.warning(
            "Could not connect to the crop "
            "suggestion service."
        )

        st.caption(
            str(exc)
        )


if suggestions:

    suggestion_df = pd.DataFrame(
        suggestions
    )

    display_columns = [

        "crop",

        "average_price",

        "market_count",

        "observations",

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
        width="stretch",
        hide_index=True
    )

    st.caption(
        "Suggestions are based on observed market "
        "activity, prices, market coverage and recent "
        "price trends in the selected district. "
        "They are market-data indicators, not guaranteed demand."
    )

else:

    st.info(
        "No crop suggestion data was available "
        "for this district."
    )


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