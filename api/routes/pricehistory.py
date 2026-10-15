"""GET /api/pricehistory/{ticker} — returns OHLCV data via yfinance for charts."""

from fastapi import APIRouter, HTTPException
import yfinance as yf
import pandas as pd

router = APIRouter()


@router.get("/pricehistory/{ticker}")
async def get_price_history(ticker: str, period: str = "3mo", interval: str = "1d") -> dict:
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
        raise HTTPException(status_code=500, detail=str(exc))
