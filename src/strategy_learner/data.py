"""FX candle data. Providers: yfinance (free, delayed) or CSV files."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

YF_INTERVAL = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "4h": "1h", "1d": "1d"}
YF_PERIOD = {"1m": "5d", "5m": "30d", "15m": "30d", "30m": "30d", "1h": "180d", "4h": "360d", "1d": "2y"}


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=str.lower)[["open", "high", "low", "close"]].dropna()
    if df.index.tz is not None:
        df.index = df.index.tz_convert("UTC").tz_localize(None)
    return df


def fetch(pair: str, tf: str, bars: int = 200, provider: str = "yfinance", csv_dir: str | None = None) -> pd.DataFrame:
    """Return candles with columns open/high/low/close and a UTC datetime index."""
    pair = pair.upper().replace("/", "")
    if provider == "csv":
        df = pd.read_csv(Path(csv_dir or ".") / f"{pair}_{tf}.csv", parse_dates=["time"], index_col="time")
        return _clean(df).tail(bars)
    if provider == "yfinance":
        import yfinance as yf
        raw = yf.download(f"{pair}=X", interval=YF_INTERVAL[tf], period=YF_PERIOD[tf], progress=False, auto_adjust=False)
        if raw.empty:
            raise RuntimeError(f"No data returned for {pair} {tf}")
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = _clean(raw)
        if tf == "4h":
            df = df.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        return df.tail(bars)
    raise ValueError(f"Unknown data provider: {provider}")


def previous_day_levels(df: pd.DataFrame, day_start_hour_utc: int = 0):
    """High/low of the previous trading day, with the day starting at day_start_hour_utc."""
    if df.empty:
        return None
    days = (df.index - pd.Timedelta(hours=day_start_hour_utc)).normalize()
    uniq = sorted(set(days))
    if len(uniq) < 2:
        return None
    prev = df[days == uniq[-2]]
    return {"date": str(uniq[-2].date()), "high": float(prev["high"].max()), "low": float(prev["low"].min())}


def facts_text(pair: str, frames: dict[str, pd.DataFrame], day_start_hour_utc: int = 0, table_rows: int = 40) -> str:
    """Exact numbers for the model, because reading prices off a picture is error-prone."""
    out = [f"PAIR: {pair}"]
    for tf, df in frames.items():
        out.append(f"\n[{tf}] last candle {df.index[-1]} close {df['close'].iloc[-1]:.5f}")
        lv = previous_day_levels(df, day_start_hour_utc)
        if lv:
            out.append(f"[{tf}] previous day ({lv['date']}) high {lv['high']:.5f} low {lv['low']:.5f}")
        out.append(f"[{tf}] last {min(table_rows, len(df))} candles (time,open,high,low,close):")
        out.append(df.tail(table_rows).round(5).to_csv(header=False))
    return "\n".join(out)
