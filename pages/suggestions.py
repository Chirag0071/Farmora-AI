import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


API_BASE = os.getenv(
    "FARMORA_API_BASE",
    "http://127.0.0.1:8000",
)


def app():

    st.markdown(
        """
        <h1 style="text-align:center;">
            🌱 Crop Suggestions
        </h1>
        """,
        unsafe_allow_html=True,
    )

    if "prediction" not in st.session_state:

        st.warning(
            "Please complete a prediction first."
        )

        if st.button(
            "Go to Prediction",
            width="content",
        ):

            st.switch_page(
                "pages/predict.py"
            )

        return

    prediction = st.session_state[
        "prediction"
    ]

    state = prediction["state"]
    district = prediction["district"]
    selected_crop = prediction["crop"]

    st.markdown(
        f"""
        <div class="glass-card">
            <h3>📍 {district}, {state}</h3>
            <p>
                Selected crop:
                <b>{selected_crop}</b>
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    payload = {
        "state": state,
        "district": district,
        "selected_crop": selected_crop,
    }

    try:

        with st.spinner(
            "Analyzing available market data..."
        ):

            response = requests.post(
                f"{API_BASE}/crop-suggestions",
                json=payload,
                timeout=180,
            )

            response.raise_for_status()

            suggestions = response.json()

    except requests.exceptions.RequestException as exc:

        st.error(
            f"Unable to generate suggestions: {exc}"
        )

        return

    except Exception as exc:

        st.error(
            f"Unexpected error: {exc}"
        )

        return

    if not suggestions:

        st.info(
            "No crop suggestions are available "
            "for this location."
        )

        return

    st.subheader(
        "🌾 Crops Showing Market Activity"
    )

    for index, item in enumerate(
        suggestions,
        start=1,
    ):

        crop_name = item.get(
            "crop",
            "Unknown",
        )

        average_price = item.get(
            "average_price",
            0,
        )

        market_count = item.get(
            "market_count",
            0,
        )

        observations = item.get(
            "observations",
            0,
        )

        st.markdown(
            f"""
            <div class="glass-card">
                <h3>
                    {index}. 🌱 {crop_name}
                </h3>

                <p>
                    Average market price:
                    <b>₹{average_price:,.0f}</b>
                </p>

                <p>
                    Markets:
                    <b>{market_count}</b>
                </p>

                <p>
                    Market observations:
                    <b>{observations}</b>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# --------------------------------------------------
# IMPORTANT: Run the Page
# --------------------------------------------------

app()