"""GET /api/pricehistory/{ticker} — returns OHLCV data via yfinance for charts."""

from fastapi import APIRouter, HTTPException, Path
import yfinance as yf
import pandas as pd

router = APIRouter()


PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y"}
INTERVALS = {"1d", "1wk", "1mo"}


# A plain def: FastAPI runs it in its thread pool, so the blocking yfinance download no longer
# freezes every other request while it runs (it was an async def; review finding F-20)
@router.get("/pricehistory/{ticker}")
def get_price_history(ticker: str = Path(pattern=r"^[A-Za-z0-9&\-]{1,20}(\.(NS|BO|ns|bo))?$"),
                      period: str = "3mo", interval: str = "1d") -> dict:
    if period not in PERIODS or interval not in INTERVALS:
        raise HTTPException(status_code=422, detail="Unsupported period or interval")
    try:
        df: pd.DataFrame = yf.download(
            ticker.upper(),
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            raise HTTPException(status_code=404, detail=f"No data found for {ticker}")

        # Flatten MultiIndex columns if present (yfinance ≥ 0.2.40)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df = df.reset_index()
        records = []
        for _, row in df.iterrows():
            records.append({
                "date":   str(row["Date"])[:10],
                "open":   round(float(row["Open"]),  2),
                "high":   round(float(row["High"]),  2),
                "low":    round(float(row["Low"]),   2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })

        return {"ticker": ticker.upper(), "period": period, "interval": interval, "candles": records}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Price data unavailable ({type(exc).__name__})")
