import os

import requests
import streamlit as st
from dotenv import load_dotenv

from utils.crops import INDIA_CROPS


load_dotenv()


API_BASE = os.environ.get(
    "FARMORA_API_BASE",
    "http://127.0.0.1:8000"
).rstrip("/")


STATES_API = (
    "https://countriesnow.space/api/v0.1/countries/states"
)

CITIES_API = (
    "https://countriesnow.space/api/v0.1/countries/state/cities"
)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
    <div class="glass-card">
        <h1>🌱 Crop Prediction</h1>
        <p>
            Enter the required details to get crop market insights.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# LOCATION HELPERS
# ============================================================

@st.cache_data(
    show_spinner=False,
    ttl=86400
)
def get_india_states():

    try:

        response = requests.post(
            STATES_API,
            json={
                "country": "India"
            },
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        states = [
            item["name"]
            for item in
            data.get(
                "data",
                {}
            ).get(
                "states",
                []
            )
        ]

        return sorted(
            states
        )

    except Exception:

        return []


@st.cache_data(
    show_spinner=False,
    ttl=86400
)
def get_state_districts(
    state_name
):

    try:

        response = requests.post(

            CITIES_API,

            json={
                "country": "India",
                "state": state_name
            },

            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        return sorted(
            data.get(
                "data",
                []
            )
        )

    except Exception:

        return []


# ============================================================
# STATES
# ============================================================

india_states = get_india_states()


if not india_states:

    st.error(
        "Couldn't load the list of states right now. "
        "Please check your internet connection."
    )


# ============================================================
# INPUTS
# ============================================================

col1, col2 = st.columns(2)


with col1:

    state = st.selectbox(
        "Select State",
        ["Select State"] +
        india_states
    )

    if state != "Select State":

        districts = get_state_districts(
            state
        )

    else:

        districts = []

    if (
        state != "Select State"
        and districts
    ):

        district = st.selectbox(
            "Select District",
            ["Select District"] +
            districts
        )

    else:

        district = st.text_input(
            "Enter District"
        )

    crop = st.selectbox(
        "Select Crop",
        ["Select Crop"] +
        INDIA_CROPS
    )


with col2:

    production_cost = st.number_input(
        "Production Cost (₹/qtl)",
        min_value=0.0,
        value=0.0,
        step=100.0
    )

    arrival_date = st.date_input(
        "Historical Arrival Date (Optional)",
        value=None
    )


# ============================================================
# SUBMIT
# ============================================================

if st.button(
    "Show Details",
    type="primary",
    width="stretch"
):

    if state == "Select State":

        st.warning(
            "Please select a state."
        )

    elif (
        not district
        or district == "Select District"
    ):

        st.warning(
            "Please enter a district."
        )

    elif crop == "Select Crop":

        st.warning(
            "Please select a crop."
        )

    else:

        selected_date = None

        if arrival_date:

            selected_date = (
                arrival_date.strftime(
                    "%d-%m-%Y"
                )
            )

        st.session_state[
            "prediction"
        ] = {

            "state":
                state,

            "district":
                district,

            "crop":
                crop,

            "production_cost":
                production_cost,

            "arrival_date":
                selected_date
        }

        st.switch_page(
            "pages/result.py"
        )