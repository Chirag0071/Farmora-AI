import os
import time

import requests
import streamlit as st
from dotenv import load_dotenv

from utils.crops import INDIA_CROPS


load_dotenv()


API_BASE = os.environ.get(
    "FARMORA_API_BASE",
    "http://127.0.0.1:8000"
).rstrip("/")



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
# LOCATION HELPERS  (state / district names come from AGMARKNET itself)
# ============================================================

def _wait_for_backend(path, params=None, max_wait=240):
    """Call the backend until the AGMARKNET location list is ready.
    Free hosts put the backend to sleep when idle; waking takes about a minute, so connection
    errors and 5xx answers are treated as "still waking up" and retried."""

    waited = 0
    last_problem = "backend not reachable"

    while waited < max_wait:

        try:

            response = requests.get(
                f"{API_BASE}{path}",
                params=params,
                timeout=30
            )

            if response.status_code < 500:

                response.raise_for_status()

                data = response.json()

                if data.get("status") == "ready":
                    return data

                if data.get("status") == "error":
                    raise RuntimeError(data.get("message") or "AGMARKNET locations unavailable")

            else:

                last_problem = f"backend answered HTTP {response.status_code}"

        except requests.exceptions.RequestException as exc:

            last_problem = type(exc).__name__

        time.sleep(3)
        waited += 3

    raise RuntimeError(f"Timed out while loading AGMARKNET locations ({last_problem})")


@st.cache_data(
    show_spinner=False,
    ttl=3600
)
def _load_states():
    # Errors are not cached by Streamlit, so a failed load is retried on the next run.
    return _wait_for_backend("/locations/states")["states"]


@st.cache_data(
    show_spinner=False,
    ttl=3600
)
def _load_districts(state_name):
    return _wait_for_backend(
        "/locations/districts",
        params={"state": state_name}
    )["districts"]


def get_india_states():

    try:

        with st.spinner("Loading states from AGMARKNET (first load can take a minute)..."):
            return _load_states()

    except Exception as exc:

        st.error(
            "Could not load states from AGMARKNET. "
            "Make sure the backend is running and your API key is valid, then reload."
        )
        st.caption(str(exc))

        return []


def get_state_districts(
    state_name
):

    try:

        return _load_districts(
            state_name
        )

    except Exception:

        return []


# ============================================================
# STATES
# ============================================================

india_states = get_india_states()


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