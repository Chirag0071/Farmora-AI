# backend/services/geocoding.py

import time

import requests


NOMINATIM_URL = (
    "https://nominatim.openstreetmap.org/search"
)

HEADERS = {
    "User-Agent":
        "Farmora/1.0 agriculture project"
}


def geocode_market(
    market,
    district,
    state
):

    queries = [

        f"{market}, {district}, {state}, India",

        f"{market}, {district}, India",

        f"{district}, {state}, India"
    ]

    for query in queries:

        try:

            response = requests.get(

                NOMINATIM_URL,

                params={
                    "q": query,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "in"
                },

                headers=HEADERS,

                timeout=15
            )

            response.raise_for_status()

            results = response.json()

            if results:

                result = results[0]

                lat = float(
                    result["lat"]
                )

                lon = float(
                    result["lon"]
                )

                time.sleep(1)

                return {
                    "market": market,
                    "lat": lat,
                    "lon": lon
                }

        except Exception as exc:

            print(
                f"Geocoding failed for "
                f"{market}: {exc}"
            )

            continue

    return None


def get_market_locations(
    state,
    district,
    crop
):

    from backend.services.agmarknet import (
        get_price_history
    )

    df = get_price_history(
        state=state,
        district=district,
        crop=crop
    )

    if df.empty:
        return []

    markets = (
        df["market"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
        .tolist()
    )

    locations = []

    for market in markets:

        location = geocode_market(
            market=market,
            district=district,
            state=state
        )

        if location:

            locations.append(
                location
            )

    return locations