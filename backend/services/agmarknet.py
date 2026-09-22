# backend/services/agmarknet.py

import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("AGMARKNET_API_KEY")

RESOURCE_ID = "35985678-0d79-46b4-9ed6-6f13308a1d24"

API_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"

HEADERS = {
    "User-Agent": "Farmora/1.0"
}


class AGMARKNETError(Exception):
    pass


def fetch_agmarknet(
    state: str,
    district: str,
    commodity: str | None = None,
    limit: int = 1000,
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

        # IMPORTANT:
        # Current resource uses capitalized field names.
        "filters[State]": state,
        "filters[District]": district,
    }

    if commodity:
        params["filters[Commodity]"] = commodity

    try:

        response = requests.get(
            API_URL,
            params=params,
            headers=HEADERS,
            timeout=30
        )

    except requests.RequestException as exc:

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

    records = data.get("records", [])

    if not isinstance(records, list):

        raise AGMARKNETError(
            "Invalid 'records' returned by AGMARKNET."
        )

    return records


def records_to_dataframe(records):

    if not records:

        return pd.DataFrame(
            columns=[
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
        )

    rows = []

    for record in records:

        rows.append({

            "state": str(
                record.get("State", "")
            ).strip(),

            "district": str(
                record.get("District", "")
            ).strip(),

            "market": str(
                record.get("Market", "")
            ).strip(),

            "commodity": str(
                record.get("Commodity", "")
            ).strip(),

            "variety": str(
                record.get("Variety", "")
            ).strip(),

            "grade": str(
                record.get("Grade", "")
            ).strip(),

            "arrival_date": record.get(
                "Arrival_Date"
            ),

            "min_price": record.get(
                "Min_Price"
            ),

            "modal_price": record.get(
                "Modal_Price"
            ),

            "max_price": record.get(
                "Max_Price"
            ),
        })

    df = pd.DataFrame(rows)

    # Dates
    df["arrival_date"] = pd.to_datetime(
        df["arrival_date"],
        format="%d/%m/%Y",
        errors="coerce"
    )

    # Prices
    for column in [
        "min_price",
        "modal_price",
        "max_price"
    ]:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    # Remove invalid price/date rows
    df = df.dropna(
        subset=[
            "arrival_date",
            "modal_price"
        ]
    )

    return df


def get_price_history(
    state: str,
    district: str,
    crop: str
):

    records = fetch_agmarknet(
        state=state,
        district=district,
        commodity=crop,
        limit=1000
    )

    df = records_to_dataframe(records)

    if df.empty:

        raise AGMARKNETError(
            f"No price data found for "
            f"{crop} in {district}, {state}."
        )

    return df


def get_latest_record(df):

    if df.empty:
        return None

    df = df.sort_values(
        "arrival_date",
        ascending=False
    )

    row = df.iloc[0]

    return {
        "date": row["arrival_date"].strftime(
            "%Y-%m-%d"
        ),

        "market": row["market"],

        "min_price": float(
            row["min_price"]
        ),

        "modal_price": float(
            row["modal_price"]
        ),

        "max_price": float(
            row["max_price"]
        )
    }


def get_monthly_history(df):

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
        .set_index("arrival_date")
        ["modal_price"]
        .resample("MS")
        .mean()
        .dropna()
        .reset_index()
    )

    monthly.rename(
        columns={
            "arrival_date": "date"
        },
        inplace=True
    )

    return monthly