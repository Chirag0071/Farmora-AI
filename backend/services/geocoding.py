import time

import requests


NOMINATIM_URL = (
    "https://nominatim.openstreetmap.org/search"
)


def geocode_market(
    market,
    district,
    state
):

    queries = [
        f"{market}, {district}, {state}, India",
        f"{market}, {district}, India",
        f"{district}, {state}, India",
    ]

    headers = {
        "User-Agent": "Farmora/1.0 agriculture project"
    }

    for query in queries:

        try:

            response = requests.get(
                NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "in",
                },
                headers=headers,
                timeout=15,
            )

            response.raise_for_status()

            results = response.json()

            if results:

                result = results[0]

                time.sleep(1)

                return {
                    "lat": float(
                        result["lat"]
                    ),
                    "lon": float(
                        result["lon"]
                    )
                }

        except Exception:

            continue

    return None


def get_market_locations(
    df,
    district,
    state
):

    locations = []

    if df.empty:

        return locations

    markets = (
        df["market"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )

    for market in markets:

        coordinates = geocode_market(
            market,
            district,
            state
        )

        if coordinates:

            locations.append({
                "market": market,
                "lat": coordinates["lat"],
                "lon": coordinates["lon"]
            })

    return locations