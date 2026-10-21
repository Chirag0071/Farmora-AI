# backend/services/agmarknet.py

import os
import json
import hashlib
from pathlib import Path
from functools import lru_cache

import pandas as pd
import requests
from dotenv import load_dotenv

from utils.crops import commodity_candidates


load_dotenv()


API_KEY = os.getenv("AGMARKNET_API_KEY")

# Live daily mandi prices (updated every day) -> "present" prices.
CURRENT_RESOURCE_ID = os.getenv(
    "AGMARKNET_RESOURCE_ID",
    "9ef84268-d588-465a-a308-a864a43d0070"
)

# Older archive of daily prices -> "past" prices.
HISTORICAL_RESOURCE_ID = "35985678-0d79-46b4-9ed6-6f13308a1d24"

RESOURCE_IDS = [CURRENT_RESOURCE_ID, HISTORICAL_RESOURCE_ID]

HEADERS = {
    "User-Agent": "Farmora/1.0"
}

# Don't let one request hang forever.
REQUEST_TIMEOUT = 20

# Records requested per page. (Some API keys cap this at 10;
# paging below handles that.)
PAGE_SIZE = 100
MAX_PAGES = 5

CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "agmarknet_cache"
CACHE_MAX_AGE_DAYS = 30


class AGMARKNETError(Exception):
    pass


_CANONICAL_KEYS = {
    "state": "State",
    "district": "District",
    "market": "Market",
    "commodity": "Commodity",
    "variety": "Variety",
    "grade": "Grade",
    "arrival_date": "Arrival_Date",
    "min_price": "Min_Price",
    "max_price": "Max_Price",
    "modal_price": "Modal_Price",
}


def _normalize_record(record: dict) -> dict:
    """Different datasets use 'state' or 'State', 'min_price' or 'Min_Price'."""
    out = {}
    for key, value in record.items():
        canonical = _CANONICAL_KEYS.get(str(key).strip().lower())
        out[canonical or key] = value
    return out


# ============================================================
# API REQUEST
# ============================================================

def _request_page(
    resource_id: str,
    state: str,
    district: str,
    commodity: str | None = None,
    limit: int = PAGE_SIZE,
    offset: int = 0,
    title_case_filters: bool = False
):

    if not API_KEY:

        raise AGMARKNETError(
            "AGMARKNET_API_KEY is missing from .env"
        )

    names = (
        ("State", "District", "Commodity")
        if title_case_filters
        else ("state", "district", "commodity")
    )

    params = {
        "api-key": API_KEY,
        "format": "json",
        "limit": limit,
        "offset": offset,
        f"filters[{names[0]}]": state,
        f"filters[{names[1]}]": district,
    }

    if commodity:

        params[f"filters[{names[2]}]"] = commodity

    try:

        response = requests.get(
            f"https://api.data.gov.in/resource/{resource_id}",
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
        # Do not include the prepared URL: it contains the API key query parameter.
        raise AGMARKNETError(
            f"Unable to connect to AGMARKNET ({type(exc).__name__}). Check internet access, firewall/proxy settings, and api.data.gov.in availability."
        )

    if response.status_code != 200:

        raise AGMARKNETError(
            f"AGMARKNET returned HTTP "
            f"{response.status_code}: "
            f"{response.text[:300]}"
        )

    try:

        data = response.json()

    except ValueError:

        raise AGMARKNETError(
            "AGMARKNET did not return valid JSON."
        )

    if data.get("status", "ok") != "ok":

        raise AGMARKNETError(
            f"AGMARKNET API error: {data.get('message', data)}"
        )

    records = data.get("records", [])

    if not isinstance(records, list):

        raise AGMARKNETError(
            "Invalid records returned by AGMARKNET."
        )

    data["records"] = [
        _normalize_record(r) for r in records
        if isinstance(r, dict)
    ]

    return data


# ============================================================
# DISK CACHE HELPERS
# ============================================================
def _cache_file(state: str, district: str, commodity: str | None, resource_id: str = HISTORICAL_RESOURCE_ID) -> Path:
    parts = [state.strip().lower(), district.strip().lower(), (commodity or "").strip().lower()]
    if resource_id != HISTORICAL_RESOURCE_ID:
        parts.append(resource_id)  # historical keeps the original key, so old cache files still work
    key = json.dumps(parts, ensure_ascii=False)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"{digest}.json"

def _read_cached_records(state: str, district: str, commodity: str | None, resource_id: str = HISTORICAL_RESOURCE_ID):
    path = _cache_file(state, district, commodity, resource_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("records", []) if isinstance(payload.get("records"), list) else []
        return [_normalize_record(r) for r in records if isinstance(r, dict)]
    except (OSError, ValueError, AttributeError):
        return []

def _write_cached_records(state: str, district: str, commodity: str | None, records, resource_id: str = HISTORICAL_RESOURCE_ID):
    path = _cache_file(state, district, commodity, resource_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"saved_at": pd.Timestamp.now(tz="UTC").isoformat(), "records": records}, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"Could not save AGMARKNET cache: {exc}")


# ============================================================
# FETCH RECORDS
# ============================================================

def _fetch_resource(resource_id, state, district, commodity):
    """Fetch all pages from one dataset. Tries lowercase filter names first,
    then Title-case, because datasets differ."""

    for title_case in (False, True):

        collected = []
        offset = 0

        for page_number in range(MAX_PAGES):

            data = _request_page(
                resource_id=resource_id,
                state=state,
                district=district,
                commodity=commodity,
                limit=PAGE_SIZE,
                offset=offset,
                title_case_filters=title_case
            )

            records = data.get("records", [])

            if not records:
                break

            collected.extend(records)
            offset += len(records)

            try:
                total = int(data.get("total", 0))
            except (TypeError, ValueError):
                total = 0

            if total and offset >= total:
                break

        if collected:
            return collected

    return []


def _dedupe(records):

    unique_records = []
    seen = set()

    for record in records:

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
            unique_records.append(record)

    return unique_records


@lru_cache(maxsize=32)
def _fetch_cached_in_memory(state, district, commodity, day):
    # `day` is part of the key so the in-memory cache refreshes daily.
    return tuple(_fetch_all(state, district, commodity))


def _fetch_all(state, district, commodity):

    all_records = []
    errors = []

    for resource_id in RESOURCE_IDS:

        try:

            records = _fetch_resource(resource_id, state, district, commodity)

            if records:
                _write_cached_records(state, district, commodity, records, resource_id)

        except AGMARKNETError as exc:

            errors.append(exc)
            records = _read_cached_records(state, district, commodity, resource_id)

            if records:
                print(f"AGMARKNET unavailable for {resource_id}; using {len(records)} cached records. Error: {exc}")

        all_records.extend(records)

    if not all_records and errors:
        raise errors[0]

    return _dedupe(all_records)


def fetch_agmarknet(
    state: str,
    district: str,
    commodity: str | None = None
):

    unique_records = list(
        _fetch_cached_in_memory(
            state,
            district,
            commodity,
            pd.Timestamp.now().strftime("%Y-%m-%d")
        )
    )

    print("Total unique AGMARKNET records:", len(unique_records))

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

    # Blank min/max prices would become NaN and break JSON output;
    # fall back to the modal price.
    df["min_price"] = df["min_price"].fillna(df["modal_price"])
    df["max_price"] = df["max_price"].fillna(df["modal_price"])

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

    df = pd.DataFrame()

    # Try the selected name first, then known AGMARKNET spellings.
    for name in commodity_candidates(crop):

        records = fetch_agmarknet(
            state,
            district,
            name
        )

        df = records_to_dataframe(
            records
        )

        if not df.empty:
            break

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