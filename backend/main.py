# backend/main.py

import pandas as pd

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.services.agmarknet import (
    AGMARKNETError,
    get_price_history,
    get_latest_record,
    get_monthly_history,
)


app = FastAPI(
    title="Farmora API",
    version="1.0"
)


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

    forecast_months: int = Field(
        default=12,
        ge=1,
        le=24
    )


@app.get("/health")
def health():

    return {
        "status": "ok",
        "service": "Farmora API"
    }


@app.post("/price-history")
def price_history(request: PriceRequest):

    print(
        f"\nFarmora request:"
        f"\nState: {request.state}"
        f"\nDistrict: {request.district}"
        f"\nCrop: {request.crop}"
    )

    try:

        df = get_price_history(
            state=request.state,
            district=request.district,
            crop=request.crop
        )

        print(
            f"AGMARKNET records received: {len(df)}"
        )

        latest = get_latest_record(df)

        monthly = get_monthly_history(df)

        records = []

        for _, row in df.iterrows():

            records.append({

                "state": row["state"],

                "district": row["district"],

                "market": row["market"],

                "commodity": row["commodity"],

                "variety": row["variety"],

                "grade": row["grade"],

                "arrival_date": (
                    row["arrival_date"]
                    .strftime("%Y-%m-%d")
                ),

                "min_price": float(
                    row["min_price"]
                ),

                "modal_price": float(
                    row["modal_price"]
                ),

                "max_price": float(
                    row["max_price"]
                )
            })

        monthly_history = []

        for _, row in monthly.iterrows():

            monthly_history.append({

                "date": row["date"].strftime(
                    "%Y-%m-%d"
                ),

                "modal_price": float(
                    row["modal_price"]
                )
            })

        return {

            "status": "success",

            "state": request.state,

            "district": request.district,

            "crop": request.crop,

            "latest": latest,

            "record_count": len(records),

            "records": records,

            "monthly_history": monthly_history,

            "forecast": []
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