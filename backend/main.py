from contextlib import asynccontextmanager
from typing import Optional
import pandas as pd
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from backend.services.agmarknet import (
    AGMARKNETError,
    get_price_history,
    get_price_by_date,
    get_latest_record,
    get_monthly_history,
    ensure_location_index,
    get_states_status,
    get_districts_status,
)

from backend.services.forecasting import (
    forecast_prices
)

from backend.services.geocoding import (
    get_market_locations,
    warm_market_locations
)

from backend.services.recommendations import (
    get_crop_suggestions
)


@asynccontextmanager
async def lifespan(_app):

    # Start building the AGMARKNET state/district list as soon as the backend starts.
    ensure_location_index()

    yield


app = FastAPI(
    title="Farmora API",
    version="1.0",
    lifespan=lifespan
)


# ============================================================
# REQUEST MODELS
# ============================================================

class PriceRequest(BaseModel):

    state: str = Field(
        ...,
        min_length=1
    )

    district: str = Field(
        ...,
        min_length=1
    )

    crop: str = Field(
        ...,
        min_length=1
    )

    arrival_date: Optional[str] = None

    forecast_months: int = Field(
        default=12,
        ge=1,
        le=24
    )


class LocationRequest(BaseModel):

    state: str = Field(
        ...,
        min_length=1
    )

    district: str = Field(
        ...,
        min_length=1
    )

    crop: str = Field(
        ...,
        min_length=1
    )


class SuggestionRequest(BaseModel):

    state: str = Field(
        ...,
        min_length=1
    )

    district: str = Field(
        ...,
        min_length=1
    )

    selected_crop: Optional[str] = None


# ============================================================
# ROOT / HEALTH
# ============================================================

@app.get("/", include_in_schema=False)
def root():

    return {
        "service": "Farmora API",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon():

    return Response(status_code=204)


@app.get("/health")
def health():

    return {
        "status": "ok",
        "service": "Farmora API"
    }


# ============================================================
# STATES / DISTRICTS (AGMARKNET spelling, used by the Predict page)
# ============================================================

@app.get("/locations/states")
def location_states():

    status = get_states_status()

    return {
        "status": status["status"],
        "message": status["error"],
        "states": status["states"]
    }


@app.get("/locations/districts")
def location_districts(state: str):

    status = get_districts_status(state)

    return {
        "status": status["status"],
        "message": status["error"],
        "state": state,
        "districts": status["districts"]
    }


# ============================================================
# PRICE HISTORY
# ============================================================

@app.post("/price-history")
def price_history(
    request: PriceRequest
):

    print(
        f"\nFarmora request:"
        f"\nState: {request.state}"
        f"\nDistrict: {request.district}"
        f"\nCrop: {request.crop}"
        f"\nArrival Date: "
        f"{request.arrival_date}"
    )

    try:

        df = get_price_history(
            state=request.state,
            district=request.district,
            crop=request.crop
        )

        print(
            "AGMARKNET records received:",
            len(df)
        )

        # ----------------------------------------------------
        # Exact date lookup
        # ----------------------------------------------------

        selected_date_records = []

        if request.arrival_date:

            date_df = get_price_by_date(
                state=request.state,
                district=request.district,
                crop=request.crop,
                arrival_date=request.arrival_date
            )

            for _, row in date_df.iterrows():

                selected_date_records.append({

                    "market": row["market"],

                    "variety": row["variety"],

                    "grade": row["grade"],

                    "arrival_date":
                        row[
                            "arrival_date"
                        ].strftime(
                            "%Y-%m-%d"
                        ),

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
                })

        # ----------------------------------------------------
        # Latest
        # ----------------------------------------------------

        latest = get_latest_record(
            df
        )

        # ----------------------------------------------------
        # Monthly history + forecast
        # If the user typed an arrival date, analyse all data from 2015 up to that
        # date and predict the 12 months after it. Otherwise use the latest data.
        # ----------------------------------------------------

        analysis_df = df

        if request.arrival_date:

            anchor = pd.to_datetime(
                request.arrival_date,
                dayfirst=True,
                errors="coerce"
            )

            if pd.notna(anchor):

                upto = df[
                    df["arrival_date"]
                    < anchor.normalize() + pd.Timedelta(days=1)
                ]

                if not upto.empty:
                    analysis_df = upto

        monthly = get_monthly_history(
            analysis_df
        )

        forecast = forecast_prices(
            monthly_history=monthly,
            periods=request.forecast_months
        )

        # Start locating the district's markets now, so the map is ready soon.
        try:
            warm_market_locations(
                request.state,
                request.district,
                df["market"].unique()
            )
        except Exception as exc:
            print("Map warm-up skipped:", repr(exc))

        # ----------------------------------------------------
        # Raw records
        # ----------------------------------------------------

        records = []

        # The result page does not use the raw rows; with 2015-today data there can be
        # 100k+ of them, so only the newest 500 are sent.
        for _, row in df.tail(500).iterrows():

            records.append({

                "state":
                    row["state"],

                "district":
                    row["district"],

                "market":
                    row["market"],

                "commodity":
                    row["commodity"],

                "variety":
                    row["variety"],

                "grade":
                    row["grade"],

                "arrival_date":
                    row[
                        "arrival_date"
                    ].strftime(
                        "%Y-%m-%d"
                    ),

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
            })

        # ----------------------------------------------------
        # Monthly JSON
        # ----------------------------------------------------

        monthly_history = []

        for _, row in monthly.iterrows():

            monthly_history.append({

                "date":
                    row["date"].strftime(
                        "%Y-%m-%d"
                    ),

                "modal_price":
                    float(
                        row["modal_price"]
                    )
            })

        # ----------------------------------------------------
        # Forecast JSON
        # ----------------------------------------------------

        forecast_records = []

        if not forecast.empty:

            for _, row in forecast.iterrows():

                forecast_records.append({

                    "date":
                        row["date"].strftime(
                            "%Y-%m-%d"
                        ),

                    "modal_price":
                        round(
                            float(
                                row[
                                    "modal_price"
                                ]
                            ),
                            2
                        )
                })

        return {

            "status":
                "success",

            "state":
                request.state,

            "district":
                request.district,

            "crop":
                request.crop,

            "latest":
                latest,

            "record_count":
                len(df),

            "records":
                records,

            "monthly_history":
                monthly_history,

            "forecast":
                forecast_records,

            "analysis": {
                "history_from":
                    monthly["date"].min().strftime("%Y-%m-%d")
                    if not monthly.empty else None,
                "history_to":
                    monthly["date"].max().strftime("%Y-%m-%d")
                    if not monthly.empty else None,
                "months_used":
                    len(monthly)
            },

            "selected_date":
                request.arrival_date,

            "selected_date_records":
                selected_date_records,

            "selected_date_count":
                len(
                    selected_date_records
                )
        }

    except AGMARKNETError as exc:

        print(
            "AGMARKNET ERROR:",
            str(exc)
        )

        raise HTTPException(
            status_code=502,
            detail=str(exc)
        )

    except Exception as exc:

        print(
            "UNEXPECTED ERROR:",
            repr(exc)
        )

        raise HTTPException(
            status_code=500,
            detail=f"Farmora error: {str(exc)}"
        )


# ============================================================
# MARKET LOCATIONS
# ============================================================

@app.post("/market-locations")
def market_locations(
    request: LocationRequest
):

    print(
        f"\nMarket location request:"
        f"\nState: {request.state}"
        f"\nDistrict: {request.district}"
        f"\nCrop: {request.crop}"
    )

    try:

        locations = get_market_locations(
            state=request.state,
            district=request.district,
            crop=request.crop
        )

        return {

            "status":
                "success",

            "state":
                request.state,

            "district":
                request.district,

            "crop":
                request.crop,

            "count":
                len(locations),

            "locations":
                locations
        }

    except AGMARKNETError as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc)
        )

    except Exception as exc:

        print(
            "LOCATION ERROR:",
            repr(exc)
        )

        raise HTTPException(
            status_code=500,
            detail=f"Market location error: {str(exc)}"
        )


# ============================================================
# CROP SUGGESTIONS
# ============================================================

@app.post("/crop-suggestions")
def crop_suggestions(
    request: SuggestionRequest
):

    print(
        f"\nCrop suggestion request:"
        f"\nState: {request.state}"
        f"\nDistrict: {request.district}"
        f"\nSelected Crop: "
        f"{request.selected_crop}"
    )

    try:

        suggestions = get_crop_suggestions(

            state=request.state,

            district=request.district,

            selected_crop=
                request.selected_crop,

            max_results=8
        )

        return {

            "status":
                "success",

            "state":
                request.state,

            "district":
                request.district,

            "suggestions":
                suggestions
        }

    except AGMARKNETError as exc:

        raise HTTPException(
            status_code=502,
            detail=str(exc)
        )

    except Exception as exc:

        print(
            "SUGGESTION ERROR:",
            repr(exc)
        )

        raise HTTPException(
            status_code=500,
            detail=f"Crop suggestion error: {str(exc)}"
        )