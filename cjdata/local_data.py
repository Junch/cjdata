"""Read-only data access helpers for cjdata."""
from __future__ import annotations

import os
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict

import numpy as np
import pandas as pd

from .utils import to_yyyymmdd

try:
    import talib  # type: ignore
except ImportError:  # pragma: no cover
    talib = None


class TrendType(Enum):
    STRONG_UPTREND = "strong_uptrend"
    WEAK_UPTREND = "weak_uptrend"
    STRONG_DOWNTREND = "strong_downtrend"
    WEAK_DOWNTREND = "weak_downtrend"
    SIDEWAYS = "sideways"
    UNCLEAR = "unclear"


class CodeFormat(Enum):
    MARKET_SUFFIX = "suffix"
    MARKET_PREFIX = "prefix"


class FinData(ABC):
    @abstractmethod
    def get_daily(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


@dataclass
class _AdjConfig:
    flag: int
    table: str


class LocalData(FinData):
    def __init__(self, path: str) -> None:
        self._path = path
        if os.name == "nt":
            self.conn = sqlite3.connect(path, check_same_thread=False)
            self.conn.execute("PRAGMA query_only = ON")
        else:
            uri = f"file:{path}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def _table_exists(self, table: str) -> bool:
        cursor = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
        )
        return cursor.fetchone() is not None

    def get_daily(self, stock_code: str, start_date: str, end_date: str, adj: str = "qfq") -> pd.DataFrame:
        adj = adj.lower()
        if adj not in ("qfq", "hfq"):
            raise ValueError("adj must be 'qfq' or 'hfq'")

        start = to_yyyymmdd(start_date)
        end = to_yyyymmdd(end_date)
        mapping = {"hfq": _AdjConfig(1, "daily_k_data"), "qfq": _AdjConfig(2, "daily_k_data")}
        config = mapping[adj]

        if self._table_exists("daily_k_data"):
            query = (
                "SELECT date AS trade_date, open, high, low, close, preclose AS pre_close, volume "
                "FROM daily_k_data WHERE code=? AND date BETWEEN ? AND ? AND (code like '000%.SH' OR code like '399%.SZ' OR adjustflag = ?) "
                "ORDER BY date"
            )
            df = pd.read_sql(
                query,
                self.conn,
                params=(stock_code, start, end, config.flag),
            )
        else:
            fallback_table = f"daily_{adj}"
            if not self._table_exists(fallback_table):
                return pd.DataFrame()
            query = (
                "SELECT trade_date, open, high, low, close, pre_close, volume "
                f"FROM {fallback_table} WHERE stock_code=? AND trade_date BETWEEN ? AND ? ORDER BY trade_date"
            )
            df = pd.read_sql(query, self.conn, params=(stock_code, start, end))

        if df.empty:
            return df

        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        df = df.set_index("trade_date").sort_index()
        return df

    def get_weekly(self, stock_code: str, start_date: str, end_date: str, adj: str = "qfq") -> pd.DataFrame:
        data = self.get_daily(stock_code, start_date, end_date, adj)
        if data.empty:
            return data
        weekly = data.resample("W-FRI").agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        return weekly.dropna()

    def get_minutes(self, stock_code: str, start_date: str, end_date: str, freq: str = "5m") -> pd.DataFrame:
        if not self._table_exists("minutes"):
            return pd.DataFrame()

        start = to_yyyymmdd(start_date)
        end = to_yyyymmdd(end_date)
        start_ts = int(pd.to_datetime(start).timestamp() * 1000)
        end_ts = int(pd.to_datetime(end).timestamp() * 1000) + 24 * 60 * 60 * 1000

        query = (
            "SELECT trade_time, time, open, high, low, close, volume, amount, pre_close "
            "FROM minutes WHERE stock_code=? AND freq=? AND time >= ? AND time < ? ORDER BY time"
        )
        df = pd.read_sql(query, self.conn, params=(stock_code, freq, start_ts, end_ts))
        if df.empty:
            return df

        df["datetime"] = pd.to_datetime(df["time"], unit="ms", utc=True)
        df["datetime"] = df["datetime"].dt.tz_convert("Asia/Shanghai").dt.tz_localize(None)
        df = df.set_index("datetime").drop(columns=["trade_time", "time", "amount", "pre_close"], errors="ignore")
        for column in ("open", "high", "low", "close", "volume"):
            df[column] = pd.to_numeric(df[column], errors="coerce")
        df = df.dropna()
        return df

    def get_price(self, stock_code: str, date: str, adj: str = "qfq") -> float:
        adj = adj.lower()
        if adj not in ("qfq", "hfq"):
            raise ValueError("adj must be 'qfq' or 'hfq'")

        target_date = to_yyyymmdd(date)
        if self._table_exists("daily_k_data"):
            flag = 1 if adj == "hfq" else 2
            query = (
                "SELECT close FROM daily_k_data WHERE code=? AND adjustflag=? AND date <= ? ORDER BY date DESC LIMIT 1"
            )
            df = pd.read_sql(query, self.conn, params=(stock_code, flag, target_date))
        else:
            table = f"daily_{adj}"
            if not self._table_exists(table):
                return 0.0
            query = (
                f"SELECT close FROM {table} WHERE stock_code=? AND trade_date <= ? ORDER BY trade_date DESC LIMIT 1"
            )
            df = pd.read_sql(query, self.conn, params=(stock_code, target_date))

        if df.empty:
            return 0.0
        return float(df.iloc[0]["close"])

    def get_stock_list_in_sector(self, sector_name: str, format: CodeFormat = CodeFormat.MARKET_SUFFIX) -> list[str]:
        df = pd.read_sql(
            "SELECT stock_code FROM sector_stocks WHERE sector_name = ?",
            self.conn,
            params=(sector_name,),
        )
        if df.empty:
            return []
        codes = df["stock_code"].tolist()
        if format == CodeFormat.MARKET_SUFFIX:
            return codes
        converted: list[str] = []
        for code in codes:
            parts = code.split(".")
            if len(parts) == 2:
                converted.append(f"{parts[1].lower()}.{parts[0]}")
            else:
                converted.append(code)
        return converted

    def get_stock_data_frame_in_sector(
        self,
        sector_name: str,
        start_date: str,
        end_date: str,
        adj: str = "hfq",
    ) -> pd.DataFrame:
        adj = adj.lower()
        if adj not in ("qfq", "hfq"):
            raise ValueError("adj must be 'qfq' or 'hfq'")

        start = to_yyyymmdd(start_date)
        end = to_yyyymmdd(end_date)
        if self._table_exists("daily_k_data"):
            flag = 1 if adj == "hfq" else 2
            query = (
                "SELECT dk.code AS stock_code, dk.date AS trade_date, dk.open, dk.high, dk.low, dk.close, dk.volume "
                "FROM daily_k_data dk JOIN sector_stocks ss ON dk.code = ss.stock_code "
                "WHERE ss.sector_name=? AND dk.date BETWEEN ? AND ? AND dk.adjustflag=? ORDER BY dk.code, dk.date"
            )
            df = pd.read_sql(query, self.conn, params=(sector_name, start, end, flag))
        else:
            table = f"daily_{adj}"
            if not self._table_exists(table):
                return pd.DataFrame()
            query = (
                f"SELECT dq.stock_code, dq.trade_date, dq.open, dq.high, dq.low, dq.close, dq.volume "
                f"FROM {table} dq JOIN sector_stocks ss ON dq.stock_code = ss.stock_code "
                "WHERE ss.sector_name=? AND dq.trade_date BETWEEN ? AND ? ORDER BY dq.stock_code, dq.trade_date"
            )
            df = pd.read_sql(query, self.conn, params=(sector_name, start, end))

        if df.empty:
            return df

        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        stocks = self.get_stock_list_in_sector(sector_name)
        if not stocks:
            return df
        dates = pd.to_datetime(df["trade_date"].drop_duplicates())
        full_index = pd.MultiIndex.from_product([stocks, dates], names=["stock_code", "trade_date"])
        df = df.set_index(["stock_code", "trade_date"]).reindex(full_index).reset_index()
        df = df.sort_values(["stock_code", "trade_date"])
        return df

    def get_trading_dates(self, market: str, start_date: str, end_date: str) -> pd.DataFrame:
        start_ts = int(pd.to_datetime(start_date).timestamp() * 1000)
        end_ts = int(pd.to_datetime(end_date).timestamp() * 1000)
        df = pd.read_sql(
            "SELECT trade_date FROM trading_days WHERE market = ? AND trade_date BETWEEN ? AND ? ORDER BY trade_date",
            self.conn,
            params=(market, start_ts, end_ts),
        )
        if df.empty:
            return df
        df["trade_date"] = df["trade_date"].apply(lambda value: datetime.fromtimestamp(value / 1000))
        return df

    def get_etf_sector_list(self) -> list[str]:
        df = pd.read_sql(
            "SELECT DISTINCT sector_name FROM sector_stocks WHERE sector_name LIKE 'ETF%'",
            self.conn,
        )
        return df["sector_name"].tolist()

    def resample_data(self, df: pd.DataFrame, target_period: str) -> pd.DataFrame:
        if df.empty:
            return df
        period_map = {
            "1m": "1T",
            "5m": "5T",
            "15m": "15T",
            "30m": "30T",
            "45m": "45T",
            "60m": "60T",
            "1h": "1H",
            "4h": "4H",
            "1d": "1D",
        }
        if target_period == "1m":
            return df
        freq = period_map.get(target_period, "15T")
        resampled = df.resample(freq).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        return resampled.dropna()

    def get_stock_name(self, stock_code: str) -> str:
        df = pd.read_sql(
            "SELECT stock_name FROM stock_basic WHERE stock_code = ?",
            self.conn,
            params=(stock_code,),
        )
        if df.empty:
            return ""
        return str(df.iloc[0]["stock_name"])

    def get_stock_name_in_sector(self, sector: str) -> pd.DataFrame:
        df = pd.read_sql(
            "SELECT sb.stock_code, sb.stock_name FROM stock_basic sb JOIN sector_stocks ss ON sb.stock_code = ss.stock_code "
            "WHERE ss.sector_name = ?",
            self.conn,
            params=(sector,),
        )
        return df

    def get_stock_volume(self, stock_code: str) -> tuple[float, float]:
        df = pd.read_sql(
            "SELECT total_volume, float_volume FROM stock_basic WHERE stock_code = ?",
            self.conn,
            params=(stock_code,),
        )
        if df.empty:
            return (0.0, 0.0)
        row = df.iloc[0]
        return (float(row["total_volume"] or 0.0), float(row["float_volume"] or 0.0))

    def get_stock_basic_by_sector(self, sector: str) -> pd.DataFrame:
        df = pd.read_sql(
            "SELECT sb.stock_code, sb.stock_name, sb.market, sb.total_volume, sb.float_volume "
            "FROM stock_basic sb JOIN sector_stocks ss ON sb.stock_code = ss.stock_code WHERE ss.sector_name = ?",
            self.conn,
            params=(sector,),
        )
        return df

    def get_dupont_data_by_sector(self, sector: str, year: int, quarter: int) -> pd.DataFrame:
        quarter_end_dates = {1: f"{year}0331", 2: f"{year}0630", 3: f"{year}0930", 4: f"{year}1231"}
        if quarter not in quarter_end_dates:
            raise ValueError("quarter must be 1, 2, 3, or 4")
        stat_date = quarter_end_dates[quarter]
        df = pd.read_sql(
            "SELECT sb.stock_code, sb.stock_name, dd.pubDate, dd.statDate, dd.dupontROE, dd.dupontAssetStoEquity, "
            "dd.dupontAssetTurn, dd.dupontPnitoni, dd.dupontNitogr, dd.dupontTaxBurden, dd.dupontIntburden, dd.dupontEbittogr "
            "FROM stock_basic sb JOIN sector_stocks ss ON sb.stock_code = ss.stock_code "
            "LEFT JOIN dupont_data dd ON sb.stock_code = dd.code AND dd.statDate = ? WHERE ss.sector_name = ?",
            self.conn,
            params=(stat_date, sector),
        )
        return df

    def search_stocks(self, search_str: str, limit: int = 20) -> list[tuple[str, str]]:
        df = pd.read_sql(
            "SELECT stock_code, stock_name FROM stock_basic WHERE stock_code LIKE ? OR stock_name LIKE ? LIMIT ?",
            self.conn,
            params=(f"%{search_str}%", f"%{search_str}%", limit),
        )
        return list(df.itertuples(index=False, name=None))

    def get_stock_returns(self, start_date: str, end_date: str, limit: int = 100) -> pd.DataFrame:
        start_ts = int(pd.to_datetime(start_date).timestamp() * 1000)
        end_ts = int(pd.to_datetime(end_date).timestamp() * 1000)
        query = f"""
            WITH 
            start_trade_date AS (
                SELECT trade_date FROM trading_days WHERE market = 'SH' AND trade_date <= {start_ts}
                ORDER BY trade_date DESC LIMIT 1
            ),
            end_trade_date AS (
                SELECT trade_date FROM trading_days WHERE market = 'SH' AND trade_date <= {end_ts}
                ORDER BY trade_date DESC LIMIT 1
            )
            SELECT t1.stock_code, b.stock_name, t1.close AS start_price, t2.close AS end_price,
                   (t2.close - t1.close) / t1.close AS return_rate,
                   datetime(s.trade_date/1000, 'unixepoch') AS start_date,
                   datetime(e.trade_date/1000, 'unixepoch') AS end_date
            FROM daily_k_data t1
            JOIN daily_k_data t2 ON t1.code = t2.code AND t1.adjustflag = 1 AND t2.adjustflag = 1
            JOIN stock_basic b ON t1.code = b.stock_code
            JOIN start_trade_date s
            JOIN end_trade_date e
            WHERE t1.date = (SELECT strftime('%Y%m%d', datetime(s.trade_date/1000, 'unixepoch')))
              AND t2.date = (SELECT strftime('%Y%m%d', datetime(e.trade_date/1000, 'unixepoch')))
            ORDER BY return_rate DESC
            LIMIT {limit}
        """
        df = pd.read_sql(query, self.conn)
        return df

    def get_stock_code_with_suffix(self, raw_code: str) -> str:
        df = pd.read_sql(
            "SELECT stock_code FROM stock_basic WHERE stock_code LIKE ?",
            self.conn,
            params=(f"{raw_code}.%",),
        )
        if df.empty:
            return ""
        return str(df.iloc[0]["stock_code"])

    def calculate_trend(self, df: pd.DataFrame) -> Optional[TrendType]:
        if talib is None or df.empty or len(df) < 30:
            return None
        try:
            close_prices = np.asarray(df["close"].astype(float).values, dtype=float)
            high_prices = np.asarray(df["high"].astype(float).values, dtype=float)
            low_prices = np.asarray(df["low"].astype(float).values, dtype=float)
            ma5 = talib.SMA(close_prices, 5)
            ma20 = talib.SMA(close_prices, 20)
            adx = talib.ADX(high_prices, low_prices, close_prices, 14)
            atr = talib.ATR(high_prices, low_prices, close_prices, 14)
        except Exception:
            return None
        if any(np.isnan(val) for val in (ma5[-1], ma20[-1], adx[-1], atr[-1])):
            return None
        if ma5[-1] > ma20[-1] and np.nanmean(np.diff(ma5[-3:])) > 0:
            return TrendType.STRONG_UPTREND if adx[-1] > 25 else TrendType.WEAK_UPTREND
        if ma5[-1] < ma20[-1] and np.nanmean(np.diff(ma20[-5:])) < 0:
            return TrendType.STRONG_DOWNTREND if adx[-1] > 25 else TrendType.WEAK_DOWNTREND
        if (
            abs(ma5[-1] - ma20[-1]) < 0.02 * close_prices[-1]
            and atr[-1] < 0.03 * close_prices[-1]
            and adx[-1] < 20
        ):
            return TrendType.SIDEWAYS
        return TrendType.UNCLEAR

    def determine_trend(
        self,
        stock_code: str,
        date: str,
        period: int = 60,
        adjust: str = "hfq",
    ) -> Optional[TrendType]:
        end_date = to_yyyymmdd(date)
        end_dt = datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - timedelta(days=int(period * 1.5))
        start_date = start_dt.strftime("%Y%m%d")
        df = self.get_daily(stock_code, start_date, end_date, adjust)
        return self.calculate_trend(df)

    def get_trend_analysis(
        self,
        stock_code: str,
        date: str,
        period: int = 60,
        adjust: str = "qfq",
    ) -> Optional[Dict[str, object]]:
        if talib is None:
            return None
        end_date = to_yyyymmdd(date)
        end_dt = datetime.strptime(end_date, "%Y%m%d")
        start_dt = end_dt - timedelta(days=int((period + 20) * 1.5))
        start_date = start_dt.strftime("%Y%m%d")
        df = self.get_daily(stock_code, start_date, end_date, adjust)
        if df.empty or len(df) < 30:
            return None
        try:
            close_prices = np.asarray(df["close"].astype(float).values, dtype=float)
            high_prices = np.asarray(df["high"].astype(float).values, dtype=float)
            low_prices = np.asarray(df["low"].astype(float).values, dtype=float)
            ma5 = talib.SMA(close_prices, 5)
            ma20 = talib.SMA(close_prices, 20)
            adx = talib.ADX(high_prices, low_prices, close_prices, 14)
            atr = talib.ATR(high_prices, low_prices, close_prices, 14)
        except Exception:
            return None
        if any(np.isnan(val) for val in (ma5[-1], ma20[-1], adx[-1], atr[-1])):
            return None
        ma5_slope = float(np.nanmean(np.diff(ma5[-3:]))) if len(ma5) >= 3 else 0.0
        ma20_slope = float(np.nanmean(np.diff(ma20[-5:]))) if len(ma20) >= 5 else 0.0
        trend = self.determine_trend(stock_code, end_date, period, adjust)
        return {
            "trend": trend.value if trend else None,
            "ma5": float(ma5[-1]),
            "ma20": float(ma20[-1]),
            "adx": float(adx[-1]),
            "atr": float(atr[-1]),
            "current_price": float(close_prices[-1]),
            "ma5_slope": ma5_slope,
            "ma20_slope": ma20_slope,
            "analysis_date": end_date,
            "stock_code": stock_code,
            "data_points": len(df),
        }

    def get_latest_date(self) -> Optional[str]:
        if not self._table_exists("daily_k_data"):
            return None
        df = pd.read_sql("SELECT MAX(date) AS latest_date FROM daily_k_data", self.conn)
        if df.empty or df.iloc[0]["latest_date"] is None:
            return None
        return str(df.iloc[0]["latest_date"])

    def close(self) -> None:
        self.conn.close()
