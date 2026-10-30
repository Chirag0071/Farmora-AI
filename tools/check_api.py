"""
Farmora API check  -  run from the project root:   python tools/check_api.py

Tells you, for YOUR data.gov.in key:
  1. how many rows one request returns (sample keys: 10)
  2. which states the API really has rows for (live dataset and historical archive)
  3. which years the historical archive covers (so you know if 2015-today exists)

Paste the output to whoever is helping you tune Farmora.
"""
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from backend.services.agmarknet import (  # noqa: E402
    CURRENT_RESOURCE_ID, HISTORICAL_RESOURCE_ID, INDIA_STATE_GROUPS,
)

KEY = os.getenv("AGMARKNET_API_KEY")
if not KEY:
    sys.exit("AGMARKNET_API_KEY is missing from .env")

URL = "https://api.data.gov.in/resource/{}"


def call(resource, filters=None, limit=1, offset=0):
    params = {"api-key": KEY, "format": "json", "limit": limit, "offset": offset}
    for name, value in (filters or {}).items():
        params[f"filters[{name}]"] = value
    last = "rate limited"
    for attempt in range(4):
        try:
            r = requests.get(URL.format(resource), params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 502, 503, 504):
                time.sleep(1 + attempt)
                continue
            return {"error": f"HTTP {r.status_code}: {r.text[:120]}"}
        except requests.RequestException as exc:
            time.sleep(1 + attempt)
            last = type(exc).__name__
    return {"error": f"network ({last})"}


def total_for(resource, filters):
    data = call(resource, filters)
    if "error" in data:
        return None, data["error"]
    rows = data.get("records", [])
    if rows and "State" in filters and str(rows[0].get("State", rows[0].get("state", ""))).strip().lower() != filters["State"].lower():
        return 0, "filter ignored"
    return int(data.get("total", 0) or 0), None


print(f"Key: {KEY[:6]}...{KEY[-4:]}  (length {len(KEY)})\n")

# ---- 1. page size
print("1) Rows returned per request")
for name, resource in (("live", CURRENT_RESOURCE_ID), ("historical", HISTORICAL_RESOURCE_ID)):
    data = call(resource, limit=1000)
    if "error" in data:
        print(f"   {name:10s}: ERROR {data['error']}")
    else:
        print(f"   {name:10s}: asked 1000, got {len(data.get('records', []))}  (dataset total rows: {data.get('total')})")

# ---- 2. states
print("\n2) States the API has rows for   (live today | historical archive)")
jobs = [(group[0], variant) for group in INDIA_STATE_GROUPS for variant in group]


def probe(job):
    group_name, variant = job
    live, e1 = total_for(CURRENT_RESOURCE_ID, {"State": variant})
    hist, e2 = total_for(HISTORICAL_RESOURCE_ID, {"State": variant})
    return group_name, variant, live, hist, e1 or e2


with ThreadPoolExecutor(max_workers=6) as pool:
    results = list(pool.map(probe, jobs))

have = set()
for group_name, variant, live, hist, err in results:
    if (live or 0) > 0 or (hist or 0) > 0:
        have.add(group_name)
        print(f"   OK   {variant:42s} live={live!s:>7}  historical={hist!s:>9}")
    elif err:
        print(f"   ???  {variant:42s} {err}")
missing = [g[0] for g in INDIA_STATE_GROUPS if g[0] not in have]
print(f"\n   -> {len(have)} of {len(INDIA_STATE_GROUPS)} states/UTs have data under at least one spelling.")
if missing:
    print("   -> no data found for:", ", ".join(missing))

# ---- 3. years
print("\n3) Historical archive: rows on probe dates (all states), per year")
probe_days = ["01/01", "15/02", "15/03", "15/04", "15/05", "15/06", "15/07", "15/08", "15/09", "15/10", "15/11", "15/12"]
years = list(range(2015, time.localtime().tm_year + 1))


def by_date(item):
    year, day = item
    count, err = total_for(HISTORICAL_RESOURCE_ID, {"Arrival_Date": f"{day}/{year}"})
    return year, count or 0


with ThreadPoolExecutor(max_workers=6) as pool:
    counts = list(pool.map(by_date, [(y, d) for y in years for d in probe_days]))

per_year = {y: 0 for y in years}
for year, count in counts:
    per_year[year] += count

for year in years:
    bar = "#" * min(40, per_year[year] // 200)
    print(f"   {year}: {per_year[year]:>8} rows on {len(probe_days)} probe days  {bar}")

covered = [y for y in years if per_year[y] > 0]
print(f"\n   -> years with data: {covered[0]}-{covered[-1]}" if covered else "\n   -> no data found for these probe dates")
print("\nDone.")
