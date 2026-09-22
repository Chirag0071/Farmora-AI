# backend/services/agmarknet.py

import os
from functools import lru_cache

import pandas as pd
import requests
from dotenv import load_dotenv


load_dotenv()


API_KEY = os.getenv("AGMARKNET_API_KEY")

RESOURCE_ID = "35985678-0d79-46b4-9ed6-6f13308a1d24"

API_URL = (
    f"https://api.data.gov.in/resource/{RESOURCE_ID}"
)

HEADERS = {
    "User-Agent": "Farmora/1.0"
}

# Keep this reasonably high, but don't let one request hang forever.
REQUEST_TIMEOUT = 60

# Number of API pages to fetch.
# The API was returning 10 records previously, so 10 pages
# gives us up to roughly 100 records without hammering the API.
MAX_PAGES = 10

PAGE_SIZE = 10


class AGMARKNETError(Exception):
    pass


# ============================================================
# API REQUEST
# ============================================================

def _request_page(
    state: str,
    district: str,
    commodity: str | None = None,
    limit: int = PAGE_SIZE,
    offset: int = 0
):

    if not API_KEY:

        raise AGMARKNETError(
            "AGMARKNET_API_KEY is missing from .env"
        )

    params = {
        "api-key": API_KEY,
        "format": "json",
        "limit": limit,
        "offset": offset,
        "filters[State]": state,
        "filters[District]": district,
    }

    if commodity:

        params[
            "filters[Commodity]"
        ] = commodity

    try:

        response = requests.get(
            API_URL,
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT
        )

    except requests.exceptions.Timeout:

        raise AGMARKNETError(
            "AGMARKNET request timed out. "
            "The government API is responding slowly. "
            "Please try again."
        )

    except requests.exceptions.RequestException as exc:

        raise AGMARKNETError(
            f"Unable to connect to AGMARKNET: {exc}"
        )

    if response.status_code != 200:

        raise AGMARKNETError(
            f"AGMARKNET returned HTTP "
            f"{response.status_code}: "
            f"{response.text[:500]}"
        )

    try:

        data = response.json()

    except ValueError:

        raise AGMARKNETError(
            "AGMARKNET did not return valid JSON."
        )

    if data.get("status") != "ok":

        raise AGMARKNETError(
            f"AGMARKNET API error: {data}"
        )

    records = data.get(
        "records",
        []
    )

    if not isinstance(records, list):

        raise AGMARKNETError(
            "Invalid records returned by AGMARKNET."
        )

    return data


# ============================================================
# FETCH RECORDS
# ============================================================

@lru_cache(maxsize=32)
def fetch_agmarknet(
    state: str,
    district: str,
    commodity: str | None = None
):

    all_records = []

    offset = 0

    for page_number in range(
        MAX_PAGES
    ):

        print(
            f"AGMARKNET request "
            f"page {page_number + 1}/"
            f"{MAX_PAGES}, "
            f"offset={offset}"
        )

        data = _request_page(
            state=state,
            district=district,
            commodity=commodity,
            limit=PAGE_SIZE,
            offset=offset
        )

        records = data.get(
            "records",
            []
        )

        if not records:
            break

        all_records.extend(
            records
        )

        offset += len(records)

        # If API gives fewer records than requested,
        # there is normally no next page.
        if len(records) < PAGE_SIZE:
            break

    # --------------------------------------------------------
    # Remove duplicates
    # --------------------------------------------------------

    unique_records = []

    seen = set()

    for record in all_records:

        key = (
            record.get("Arrival_Date"),
            record.get("Commodity"),
            record.get("Market"),
            record.get("Variety"),
            record.get("Grade"),
            record.get("Modal_Price")
        )

        if key not in seen:

            seen.add(key)

            unique_records.append(
                record
            )

    print(
        "Total unique AGMARKNET records:",
        len(unique_records)
    )

    return unique_records


# ============================================================
# DATAFRAME
# ============================================================

def records_to_dataframe(
    records
):

    columns = [
        "state",
        "district",
        "market",
        "commodity",
        "variety",
        "grade",
        "arrival_date",
        "min_price",
        "modal_price",
        "max_price",
    ]

    if not records:

        return pd.DataFrame(
            columns=columns
        )

    rows = []

    for record in records:

        rows.append({

            "state":
                str(
                    record.get(
                        "State",
                        ""
                    )
                ).strip(),

            "district":
                str(
                    record.get(
                        "District",
                        ""
                    )
                ).strip(),

            "market":
                str(
                    record.get(
                        "Market",
                        ""
                    )
                ).strip(),

            "commodity":
                str(
                    record.get(
                        "Commodity",
                        ""
                    )
                ).strip(),

            "variety":
                str(
                    record.get(
                        "Variety",
                        ""
                    )
                ).strip(),

            "grade":
                str(
                    record.get(
                        "Grade",
                        ""
                    )
                ).strip(),

            "arrival_date":
                record.get(
                    "Arrival_Date"
                ),

            "min_price":
                record.get(
                    "Min_Price"
                ),

            "modal_price":
                record.get(
                    "Modal_Price"
                ),

            "max_price":
                record.get(
                    "Max_Price"
                )
        })

    df = pd.DataFrame(
        rows
    )

    # --------------------------------------------------------
    # Date
    # --------------------------------------------------------

    df["arrival_date"] = pd.to_datetime(
        df["arrival_date"],
        dayfirst=True,
        errors="coerce"
    )

    # --------------------------------------------------------
    # Prices
    # --------------------------------------------------------

    for column in [
        "min_price",
        "modal_price",
        "max_price"
    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # --------------------------------------------------------
    # Remove invalid rows
    # --------------------------------------------------------

    df = df.dropna(
        subset=[
            "arrival_date",
            "modal_price"
        ]
    )

    df = (
        df
        .sort_values(
            "arrival_date"
        )
        .drop_duplicates()
        .reset_index(
            drop=True
        )
    )

    return df


# ============================================================
# PRICE HISTORY
# ============================================================

def get_price_history(
    state: str,
    district: str,
    crop: str
):

    records = fetch_agmarknet(
        state,
        district,
        crop
    )

    df = records_to_dataframe(
        records
    )

    if df.empty:

        raise AGMARKNETError(
            f"No price data found for "
            f"{crop} in {district}, {state}."
        )

    return df


# ============================================================
# EXACT DATE
# ============================================================

def get_price_by_date(
    state: str,
    district: str,
    crop: str,
    arrival_date: str
):

    df = get_price_history(
        state,
        district,
        crop
    )

    try:

        target_date = pd.to_datetime(
            arrival_date,
            dayfirst=True,
            errors="raise"
        ).normalize()

    except Exception:

        raise AGMARKNETError(
            "Invalid arrival date. "
            "Please use DD-MM-YYYY."
        )

    return df[
        df["arrival_date"].dt.normalize()
        == target_date
    ].copy()


# ============================================================
# LATEST
# ============================================================

def get_latest_record(
    df
):

    if df.empty:

        return None

    temp = (
        df
        .sort_values(
            "arrival_date",
            ascending=False
        )
    )

    row = temp.iloc[0]

    return {

        "date":
            row["arrival_date"].strftime(
                "%Y-%m-%d"
            ),

        "market":
            row["market"],

        "min_price":
            float(
                row["min_price"]
            ),

        "modal_price":
            float(
                row["modal_price"]
            ),

        "max_price":
            float(
                row["max_price"]
            )
    }


# ============================================================
# MONTHLY
# ============================================================

def get_monthly_history(
    df
):

    if df.empty:

        return pd.DataFrame(
            columns=[
                "date",
                "modal_price"
            ]
        )

    temp = df.copy()

    temp = temp.dropna(
        subset=[
            "arrival_date",
            "modal_price"
        ]
    )

    monthly = (
        temp
        .set_index(
            "arrival_date"
        )
        ["modal_price"]
        .resample("MS")
        .mean()
        .dropna()
        .reset_index()
    )

    monthly.rename(
        columns={
            "arrival_date":
                "date"
        },
        inplace=True
    )

    return monthly