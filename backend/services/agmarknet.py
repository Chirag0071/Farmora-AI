import os
import re
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor
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

# data.gov.in sits behind a firewall that can reject bare python-requests traffic coming from
# cloud servers (HTTP 502). A descriptive, browser-compatible User-Agent avoids that.
HEADERS = {
    "User-Agent": os.getenv(
        "AGMARKNET_USER_AGENT",
        "Mozilla/5.0 (compatible; Farmora/1.0; agriculture price project)"
    ),
    "Accept": "application/json",
}

# Don't let one request hang forever.
REQUEST_TIMEOUT = 20

# ------------------------------------------------------------------
# FIX: the old code stopped after 5 pages x 100 = 500 records, so the
# history was truncated and the ML model starved. We now keep paging
# until the API has no more rows, bounded by a record cap and a time cap.
# All three can be changed from .env.
# ------------------------------------------------------------------
PAGE_SIZE = int(os.getenv("AGMARKNET_PAGE_SIZE", "1000"))
MAX_RECORDS = int(os.getenv("AGMARKNET_MAX_RECORDS", "100000"))      # ~5 years of daily rows for a district + crop
MAX_FETCH_SECONDS = int(os.getenv("AGMARKNET_MAX_FETCH_SECONDS", "90"))
# Parallel requests. The sample key on data.gov.in returns only 10 rows per call, so a
# 5-year history needs hundreds of calls - they are sent in parallel to stay fast.
FETCH_WORKERS = int(os.getenv("AGMARKNET_WORKERS", "3"))

# Monthly history / forecast training data starts in this year (2015 -> today).
# If the API has nothing that old, the oldest data it does have is used.
HISTORY_START_YEAR = int(os.getenv("FARMORA_HISTORY_START_YEAR", "2015"))


class AGMARKNETError(Exception):
    pass


_COOLDOWN_UNTIL = 0.0          # shared pause after a 429, so all threads back off together
_RATE_STREAK = 0


class AGMARKNETRateLimit(AGMARKNETError):
    pass


class AGMARKNETFilterError(AGMARKNETError):
    """HTTP 4xx from the API - usually means the filter field name/style is wrong."""


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
# STATE / DISTRICT NAME MATCHING
# ============================================================
# The dropdowns come from countriesnow.space, but AGMARKNET spells many
# states/districts differently, so a plain filter returns 0 rows.
# We try the original spelling first, then known alternatives.

STATE_ALIASES = {
    "delhi": ["NCT of Delhi", "Delhi"],
    "nct of delhi": ["NCT of Delhi", "Delhi"],
    "uttarakhand": ["Uttrakhand", "Uttarakhand"],
    "chhattisgarh": ["Chattisgarh", "Chhattisgarh"],
    "odisha": ["Odisha", "Orissa"],
    "puducherry": ["Pondicherry", "Puducherry"],
    "andaman and nicobar islands": ["Andaman and Nicobar", "Andaman and Nicobar Islands"],
    "jammu and kashmir": ["Jammu and Kashmir", "Jammu & Kashmir"],
    "dadra and nagar haveli and daman and diu": ["Dadra and Nagar Haveli", "Daman and Diu"],
}

_DISTRICT_PAIRS = [
    ("Gurugram", "Gurgaon"), ("Prayagraj", "Allahabad"), ("Ayodhya", "Faizabad"),
    ("Bengaluru", "Bangalore"), ("Bengaluru Urban", "Bangalore"), ("Bengaluru Rural", "Bangalore Rural"),
    ("Mysuru", "Mysore"), ("Belagavi", "Belgaum"), ("Kalaburagi", "Gulbarga"),
    ("Vijayapura", "Bijapur"), ("Ballari", "Bellary"), ("Shivamogga", "Shimoga"),
    ("Tumakuru", "Tumkur"), ("Mangaluru", "Dakshina Kannada"),
    ("Thiruvananthapuram", "Trivandrum"), ("Kozhikode", "Calicut"), ("Alappuzha", "Alleppey"),
    ("Visakhapatnam", "Vishakhapatnam"), ("Vadodara", "Baroda"), ("Puducherry", "Pondicherry"),
    ("Ahilyanagar", "Ahmednagar"), ("Chhatrapati Sambhajinagar", "Aurangabad"),
    ("Dharashiv", "Osmanabad"), ("Kanpur Nagar", "Kanpur"), ("Lakhimpur Kheri", "Kheri"),
    ("Hathras", "Mahamaya Nagar"), ("Amethi", "Sultanpur"), ("Prayagraj", "Allahabad"),
    ("Bardhaman", "Burdwan"), ("Purba Bardhaman", "Burdwan"), ("Kolkata", "Calcutta"),
    ("Thoothukkudi", "Tuticorin"), ("Tiruchirappalli", "Trichy"), ("Kancheepuram", "Kanchipuram"),
    ("Nashik", "Nasik"), ("Raigad", "Raigarh"), ("Sri Ganganagar", "Ganganagar"),
    ("Mumbai", "Mumbai City"), ("Jalandhar", "Jullundur"), ("Pune", "Poona"),
]
DISTRICT_ALIASES: dict[str, list[str]] = {}
for _a, _b in _DISTRICT_PAIRS:
    DISTRICT_ALIASES.setdefault(_a.lower(), []).append(_b)
    DISTRICT_ALIASES.setdefault(_b.lower(), []).append(_a)


def _unique(items):
    seen, out = set(), []
    for item in items:
        item = re.sub(r"\s+", " ", str(item)).strip()
        if item and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out


def _state_variants(state: str) -> list[str]:
    base = state.strip()
    return _unique([base] + STATE_ALIASES.get(base.lower(), []) + [base.replace("&", "and")])


def _district_variants(district: str) -> list[str]:
    base = district.strip()
    stripped = re.sub(r"\b(district|dist\.?|urban|rural|city)\b", "", base, flags=re.I)
    candidates = [base, stripped, base.title(), base.replace("&", "and")]
    for name in list(candidates):
        candidates += DISTRICT_ALIASES.get(re.sub(r"\s+", " ", name).strip().lower(), [])
    return _unique(candidates)


_RESOLVED_NAMES: dict[tuple[str, str], tuple[str, str]] = {}


def _same(a, b) -> bool:
    return str(a).strip().lower() == str(b).strip().lower()


def _row_matches(record, state, district, commodity) -> bool:
    """True if a returned row really belongs to the requested state/district/commodity.
    Guards against a filter name the API silently ignores (it would then return ANY state's rows)."""
    return (
        (not state or _same(record.get("State", ""), state))
        and (not district or _same(record.get("District", ""), district))
        and (not commodity or _same(record.get("Commodity", ""), commodity))
    )


def _exists(state: str, district: str | None) -> bool:
    """True if any dataset has at least one row for this state(/district). One tiny request each."""
    for resource_id in RESOURCE_IDS:
        for title_case in (True, False):
            try:
                data = _request_page(resource_id, state, district, limit=1, title_case_filters=title_case)
            except AGMARKNETFilterError:
                continue
            records = data.get("records", [])
            if records:
                if _row_matches(records[0], state, district, None):
                    return True
                continue        # this filter style was ignored by the API -> try the other one
            break               # request worked but returned nothing; no need for the other filter style
    return False


def resolve_names(state: str, district: str) -> tuple[str, str]:
    """Return the (state, district) spelling that AGMARKNET actually has data for."""
    key = (state.strip().lower(), district.strip().lower())
    if key in _RESOLVED_NAMES:
        return _RESOLVED_NAMES[key]

    try:
        if _exists(state, district):                     # usual case: 1-2 requests
            result = (state, district)
        else:
            result = None
            for s in _state_variants(state):
                if not _exists(s, None):
                    continue
                for d in _district_variants(district):
                    if _exists(s, d):
                        result = (s, d)
                        break
                if result:
                    break
            if result is None:
                result = (state, district)               # nothing matched; keep original
                print(f"AGMARKNET: no rows found for {district}, {state} under any known spelling.")
            else:
                print(f"AGMARKNET: matched {district}, {state} -> {result[1]}, {result[0]}")
    except AGMARKNETError:
        return state, district                           # API problem: don't cache, let the real fetch report it

    _RESOLVED_NAMES[key] = result
    return result


# ============================================================
# API REQUEST
# ============================================================

def _request_page(
    resource_id: str,
    state: str | None,
    district: str | None,
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
    }

    if state:

        params[f"filters[{names[0]}]"] = state

    if district:

        params[f"filters[{names[1]}]"] = district

    if commodity:

        params[f"filters[{names[2]}]"] = commodity

    global _COOLDOWN_UNTIL, _RATE_STREAK
    wait = _COOLDOWN_UNTIL - time.monotonic()
    if wait > 0:
        time.sleep(min(wait, 20))

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

    if response.status_code == 429:
        _RATE_STREAK = min(_RATE_STREAK + 1, 6)
        try:
            pause = float(response.headers.get("Retry-After", ""))
        except ValueError:
            pause = 3.0 * _RATE_STREAK
        _COOLDOWN_UNTIL = max(_COOLDOWN_UNTIL, time.monotonic() + min(pause, 20))
        raise AGMARKNETRateLimit(
            "AGMARKNET rate limit reached (HTTP 429). The sample API key allows very few "
            "requests; wait a minute or use your own data.gov.in key."
        )
    if response.status_code == 200:
        _RATE_STREAK = 0

    if response.status_code != 200:

        error_class = (
            AGMARKNETFilterError
            if response.status_code in (400, 404, 422)
            else AGMARKNETError
        )

        raise error_class(
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
# FETCH RECORDS
# ============================================================

def _to_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _fetch_offsets(resource_id, state, district, commodity, title_case, offsets, step, deadline):
    """Fetch many pages in parallel. Pages are requested in shuffled order, so even if the
    time limit hits first, the rows we got cover ALL years evenly (not just the oldest)."""

    failed = []

    def work(offset):
        for attempt in range(6):
            if time.monotonic() > deadline:
                return []
            try:
                data = _request_page(
                    resource_id, state, district, commodity,
                    limit=step, offset=offset, title_case_filters=title_case,
                )
                return data.get("records", [])
            except AGMARKNETFilterError:
                return []
            except AGMARKNETError:
                time.sleep(0.5 * (attempt + 1))      # hiccup: back off (429 also uses shared cooldown)
        failed.append(offset)
        return []

    rows = []
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        for chunk in pool.map(work, offsets):
            rows.extend(chunk)
    if failed:
        print(f"AGMARKNET: {len(failed)} of {len(offsets)} pages failed (rate limit / timeout). "
              f"Lower AGMARKNET_WORKERS or use your own API key.")
    return rows


def _fetch_resource(resource_id, state, district, commodity, max_seconds=None):
    """Fetch (up to MAX_RECORDS / MAX_FETCH_SECONDS) rows from one dataset: first page to learn
    the total + the server's real page size, then all remaining pages in parallel.
    Tries the documented Title-case filter names (filters[State]) first, then lowercase."""

    last_error = None
    request_worked = False
    deadline = time.monotonic() + (max_seconds or MAX_FETCH_SECONDS)

    for title_case in (True, False):

        try:

            first = _request_page(
                resource_id, state, district, commodity,
                limit=PAGE_SIZE, offset=0, title_case_filters=title_case
            )

        except AGMARKNETFilterError as exc:
            last_error = exc            # wrong filter style -> try the other one
            continue

        request_worked = True
        collected = list(first.get("records", []))

        if not collected:
            continue

        if not _row_matches(collected[0], state, district, commodity):
            print(f"AGMARKNET: filter style ignored by {resource_id[:8]} (rows do not match "
                  f"{state}/{district}/{commodity}); trying the other style.")
            continue

        total = min(_to_int(first.get("total")), MAX_RECORDS)
        step = len(collected)           # the server may cap the page size (e.g. 10)

        if total > step:

            offsets = list(range(step, total, step))
            random.Random(7).shuffle(offsets)

            collected += _fetch_offsets(
                resource_id, state, district, commodity,
                title_case, offsets, step, deadline
            )

            print(
                f"AGMARKNET {resource_id[:8]}: fetched {len(collected)} of {total} rows "
                f"(page size {step})"
            )

        return collected

    if last_error and not request_worked:
        raise last_error

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


@lru_cache(maxsize=8)
def _fetch_cached_in_memory(state, district, commodity, day):
    # `day` is part of the key so the in-memory cache refreshes daily.
    return tuple(_fetch_all(state, district, commodity))


def _fetch_all(state, district, commodity):
    """Always live: queries both data.gov.in datasets. No disk cache, no offline fallback."""

    all_records = []
    errors = []

    # Use the spelling AGMARKNET really has (e.g. Delhi -> NCT of Delhi).
    api_state, api_district = resolve_names(state, district)

    for resource_id in RESOURCE_IDS:

        try:

            all_records.extend(
                _fetch_resource(resource_id, api_state, api_district, commodity)
            )

        except AGMARKNETError as exc:

            errors.append(exc)
            print(f"AGMARKNET request failed for {resource_id}: {exc}")

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

            "state": str(record.get("State", "")).strip(),
            "district": str(record.get("District", "")).strip(),
            "market": str(record.get("Market", "")).strip(),
            "commodity": str(record.get("Commodity", "")).strip(),
            "variety": str(record.get("Variety", "")).strip(),
            "grade": str(record.get("Grade", "")).strip(),
            "arrival_date": record.get("Arrival_Date"),
            "min_price": record.get("Min_Price"),
            "modal_price": record.get("Modal_Price"),
            "max_price": record.get("Max_Price"),
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
    # Remove invalid rows (missing date/price, or non-positive price:
    # AGMARKNET sometimes reports 0 for "no trade", which would wreck the ML model)
    # --------------------------------------------------------

    df = df.dropna(
        subset=[
            "arrival_date",
            "modal_price"
        ]
    )

    df = df[df["modal_price"] > 0]

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
# STATES AND DISTRICTS, CONFIRMED BY THE AGMARKNET API ITSELF
# ============================================================
# The dropdowns must use AGMARKNET's own spelling (e.g. "NCT of Delhi", "Uttrakhand").
#
# States   : every Indian state / UT is asked of the API ("do you have rows for this name?").
#            Only names the API confirms are shown, in the spelling the API accepted.
#            This is ~40 tiny requests, so the list appears within seconds.
# Districts: collected per state, when a state is chosen: all of today's rows (live dataset)
#            plus a spread-out sample of the historical archive, so districts that did not
#            report today still show up.

# Each group = the spellings AGMARKNET may use for one state / UT (first one that works wins).
INDIA_STATE_GROUPS = [
    ["Andaman and Nicobar", "Andaman and Nicobar Islands", "Andaman & Nicobar Islands"],
    ["Andhra Pradesh"], ["Arunachal Pradesh"], ["Assam"], ["Bihar"], ["Chandigarh"],
    ["Chattisgarh", "Chhattisgarh"],
    ["Dadra and Nagar Haveli", "Dadra & Nagar Haveli", "Dadra and Nagar Haveli and Daman and Diu"],
    ["Daman and Diu", "Daman & Diu"],
    ["NCT of Delhi", "Delhi"],
    ["Goa"], ["Gujarat"], ["Haryana"], ["Himachal Pradesh"],
    ["Jammu and Kashmir", "Jammu & Kashmir"],
    ["Jharkhand"], ["Karnataka"], ["Kerala"], ["Ladakh"], ["Lakshadweep"],
    ["Madhya Pradesh"], ["Maharashtra"], ["Manipur"], ["Meghalaya"], ["Mizoram"], ["Nagaland"],
    ["Odisha", "Orissa"],
    ["Pondicherry", "Puducherry"],
    ["Punjab"], ["Rajasthan"], ["Sikkim"], ["Tamil Nadu"], ["Telangana"], ["Tripura"],
    ["Uttar Pradesh"],
    ["Uttrakhand", "Uttarakhand"],
    ["West Bengal"],
]

DISTRICT_SAMPLE_PAGES = int(os.getenv("FARMORA_DISTRICT_SAMPLE_PAGES", "300"))
DISTRICT_SECONDS = int(os.getenv("FARMORA_DISTRICT_SECONDS", "40"))

_STATES = {"day": None, "data": None, "loading": False, "error": None, "failed_at": 0.0}
_DISTRICTS = {}
_LOCATIONS_LOCK = threading.Lock()


def _today():
    return pd.Timestamp.now().strftime("%Y-%m-%d")


def _probe_states():

    errors = []

    def check(group):
        for name in group:
            for attempt in range(4):                  # throttled (429) / timeout: wait and retry
                try:
                    if _exists(name, None):
                        return name
                    break                             # API answered: no rows under this spelling
                except AGMARKNETError as exc:
                    if attempt == 3:
                        errors.append(exc)
                    else:
                        time.sleep(0.7 * (attempt + 1))
        return None

    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        found = [name for name in pool.map(check, INDIA_STATE_GROUPS) if name]

    if not found:
        raise errors[0] if errors else AGMARKNETError("AGMARKNET returned no states.")

    print(f"AGMARKNET states confirmed by API: {len(found)} -> {sorted(found)}")

    return sorted(found)


def _states_worker(today):

    try:

        data = _probe_states()

        with _LOCATIONS_LOCK:
            _STATES.update(day=today, data=data, error=None)

    except Exception as exc:

        print("State list failed:", repr(exc))

        with _LOCATIONS_LOCK:
            _STATES.update(error=str(exc), failed_at=time.monotonic())

    finally:

        with _LOCATIONS_LOCK:
            _STATES["loading"] = False


def ensure_location_index():
    """Start (or refresh once a day) the background check of which states AGMARKNET has."""

    today = _today()

    with _LOCATIONS_LOCK:

        fresh = _STATES["data"] is not None and _STATES["day"] == today
        retry_later = _STATES["error"] and time.monotonic() - _STATES["failed_at"] < 30

        if fresh or _STATES["loading"] or retry_later:
            return

        _STATES["loading"] = True

    threading.Thread(target=_states_worker, args=(today,), daemon=True).start()


def get_states_status():
    """{'status': 'ready' | 'loading' | 'error', 'states': [...], 'error': str}"""

    ensure_location_index()

    with _LOCATIONS_LOCK:

        if _STATES["data"] is not None:
            return {"status": "ready", "states": list(_STATES["data"]), "error": None}

        if _STATES["loading"]:
            return {"status": "loading", "states": [], "error": None}

        return {"status": "error", "states": [], "error": _STATES["error"]}


def _sample_resource(resource_id, state, max_pages, max_seconds):
    """Spread-out sample of one state's rows (random pages across the whole table)."""

    deadline = time.monotonic() + max_seconds

    for title_case in (True, False):

        try:
            first = _request_page(
                resource_id, state, None, None,
                limit=PAGE_SIZE, offset=0, title_case_filters=title_case
            )
        except AGMARKNETFilterError:
            continue

        rows = list(first.get("records", []))

        if not rows or not _row_matches(rows[0], state, None, None):
            continue

        total = _to_int(first.get("total"))
        step = len(rows)

        offsets = list(range(step, total, step))
        random.Random(11).shuffle(offsets)

        rows += _fetch_offsets(
            resource_id, state, None, None, title_case,
            offsets[:max(max_pages - 1, 0)], step, deadline
        )

        return rows

    return []


def _districts_worker(state, key, today):

    names, errors = set(), []

    for resource_id, fetch in (
        (CURRENT_RESOURCE_ID, lambda r: _fetch_resource(r, state, None, None, max_seconds=15)),
        (HISTORICAL_RESOURCE_ID, lambda r: _sample_resource(r, state, DISTRICT_SAMPLE_PAGES, DISTRICT_SECONDS)),
    ):

        try:

            for record in fetch(resource_id):
                district = str(record.get("District", "")).strip()
                if district:
                    names.add(district)

        except AGMARKNETError as exc:
            errors.append(exc)

    with _LOCATIONS_LOCK:

        if names:
            _DISTRICTS[key].update(day=today, data=sorted(names), error=None)
            print(f"AGMARKNET districts for {state}: {len(names)}")
        else:
            _DISTRICTS[key].update(error=str(errors[0]) if errors else "No districts found.", failed_at=time.monotonic())

        _DISTRICTS[key]["loading"] = False


def get_districts_status(state):
    """{'status': 'ready' | 'loading' | 'error', 'districts': [...], 'error': str} for one state."""

    key = state.strip().lower()
    today = _today()

    with _LOCATIONS_LOCK:

        entry = _DISTRICTS.setdefault(key, {"day": None, "data": None, "loading": False, "error": None, "failed_at": 0.0})

        fresh = entry["data"] is not None and entry["day"] == today
        retry_later = entry["error"] and time.monotonic() - entry["failed_at"] < 30

        if not fresh and not entry["loading"] and not retry_later:
            entry["loading"] = True
            threading.Thread(target=_districts_worker, args=(state.strip(), key, today), daemon=True).start()

        if entry["data"] is not None and (fresh or entry["loading"]):
            return {"status": "ready", "districts": list(entry["data"]), "error": None}

        if entry["loading"]:
            return {"status": "loading", "districts": [], "error": None}

        if entry["data"] is not None:
            return {"status": "ready", "districts": list(entry["data"]), "error": None}

        return {"status": "error", "districts": [], "error": entry["error"]}


# ============================================================
# ALL MARKETS OF A DISTRICT (used by the map)
# ============================================================

def get_district_markets(
    state: str,
    district: str
):
    """Mandis currently reporting in this district (live dataset, one small request).
    Deliberately NOT the 5-year history, which would take minutes just to list market names."""

    api_state, api_district = resolve_names(state, district)

    try:

        records = _fetch_resource(
            CURRENT_RESOURCE_ID, api_state, api_district, None
        )

    except AGMARKNETError:

        return []

    return sorted(
        {str(r.get("Market", "")).strip() for r in records if r.get("Market")}
    )


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

        "date": row["arrival_date"].strftime("%Y-%m-%d"),

        "market": row["market"],

        "min_price": float(row["min_price"]),

        "modal_price": float(row["modal_price"]),

        "max_price": float(row["max_price"])
    }


# ============================================================
# MONTHLY
# ============================================================

def get_monthly_history(
    df,
    start_year: int = HISTORY_START_YEAR
):
    """Monthly modal price from `start_year` (default 2015) up to the latest data.

    Robust version: each month is the MEDIAN of the reported modal prices (a few expensive
    varieties or typo prices cannot drag it), months with very few observations are
    treated as missing and interpolated, and isolated spikes far from their neighbours
    are pulled back to the local level. The last month stays the real latest median.
    """

    columns = ["date", "modal_price"]

    if df.empty:
        return pd.DataFrame(columns=columns)

    temp = df.dropna(subset=["arrival_date", "modal_price"])
    temp = temp[temp["modal_price"] > 0]

    if temp.empty:
        return pd.DataFrame(columns=columns)

    since = temp[temp["arrival_date"] >= pd.Timestamp(year=start_year, month=1, day=1)]

    if not since.empty:         # if the API has nothing that recent, use whatever it has
        temp = since

    # Drop absurd rows (typos / other units) relative to the overall typical price.
    typical = float(temp["modal_price"].median())
    temp = temp[(temp["modal_price"] >= typical / 8) & (temp["modal_price"] <= typical * 8)]

    temp = temp.assign(month=temp["arrival_date"].dt.to_period("M").dt.to_timestamp())

    grouped = temp.groupby("month")["modal_price"]
    median = grouped.median()
    count = grouped.size()

    full_index = pd.date_range(median.index.min(), median.index.max(), freq="MS")
    series = median.reindex(full_index)
    counts = count.reindex(full_index).fillna(0)

    # Months with too few observations are unreliable (keep the latest month anyway).
    weak = counts < 3
    weak.iloc[-1] = False
    series[weak] = float("nan")

    # Pull isolated spikes back towards the local level.
    local = series.rolling(7, center=True, min_periods=3).median()
    spike = (series > local * 2.0) | (series < local * 0.5)
    series[spike.fillna(False)] = local[spike.fillna(False)]

    series = series.interpolate(limit_direction="both")

    monthly = (
        pd.DataFrame({"date": series.index, "modal_price": series.values})
        .dropna()
        .reset_index(drop=True)
    )

    return monthly