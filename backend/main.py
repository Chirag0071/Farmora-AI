# backend/main.py

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.services.agmarknet import (
    AGMARKNETError,
    get_price_history,
    get_price_by_date,
    get_latest_record,
    get_monthly_history,
)

from backend.services.forecasting import (
    forecast_prices
)

from backend.services.geocoding import (
    get_market_locations
)

from backend.services.recommendations import (
    get_crop_suggestions
)


app = FastAPI(
    title="Farmora API",
    version="1.0"
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
# HEALTH
# ============================================================

@app.get("/health")
def health():

    return {
        "status": "ok",
        "service": "Farmora API"
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
        # Monthly history
        # ----------------------------------------------------

        monthly = get_monthly_history(
            df
        )

        # ----------------------------------------------------
        # Forecast
        # ----------------------------------------------------

        forecast = forecast_prices(
            monthly_history=monthly,
            periods=request.forecast_months
        )

        # ----------------------------------------------------
        # Raw records
        # ----------------------------------------------------

        records = []

        for _, row in df.iterrows():

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
                len(records),

            "records":
                records,

            "monthly_history":
                monthly_history,

            "forecast":
                forecast_records,

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