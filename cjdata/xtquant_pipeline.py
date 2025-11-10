"""Data acquisition routines backed by xtquant."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional, Sequence, Any, TYPE_CHECKING

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype

from .db import UpsertSpec, insert_ignore, upsert_rows
from .utils import to_yyyymmdd

try:  # pragma: no cover - optional dependency
    from tqdm import tqdm  # type: ignore
except ImportError:  # pragma: no cover
    tqdm = None  # type: ignore

xtdata: Any
if TYPE_CHECKING:  # pragma: no cover
    from xtquant import xtdata as _xtdata

try:  # pragma: no cover - optional dependency
    from xtquant import xtdata as _xtdata  # type: ignore
    xtdata = _xtdata
except ImportError:  # pragma: no cover
    xtdata = None

_LOGGER = logging.getLogger(__name__)


def _require_xtquant() -> None:
    if xtdata is None:  # pragma: no cover
        raise RuntimeError("xtquant is not installed. Install xtquant to use this feature.")


def _to_epoch_ms(value: Any) -> int:
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    return int(pd.Timestamp(value).timestamp() * 1000)


class XtQuantPipeline:
    def __init__(self, conn, logger: Optional[logging.Logger] = None) -> None:
        _require_xtquant()
        self.conn = conn
        self.logger = logger or _LOGGER

    def download_trading_calendar(self, markets: Sequence[str] = ("SH", "SZ")) -> int:
        total = 0
        for market in markets:
            dates = xtdata.get_trading_dates(market)
            if not dates:
                continue
            rows = [(market, _to_epoch_ms(day)) for day in dates]
            total += insert_ignore(self.conn, "trading_days", ("market", "trade_date"), rows)
        self.conn.commit()
        return total

    def update_sector_membership(self) -> int:
        sectors = xtdata.get_sector_list()
        total = 0
        for sector in sectors:
            stocks = xtdata.get_stock_list_in_sector(sector)
            rows = [(sector, code) for code in stocks]
            total += insert_ignore(self.conn, "sector_stocks", ("sector_name", "stock_code"), rows)
        self.conn.commit()
        return total

    def update_stock_basic(self, sectors: Sequence[str] = ("沪深A股", "沪深指数", "沪深基金")) -> int:
        cursor = self.conn.execute(
            "SELECT DISTINCT stock_code FROM sector_stocks WHERE sector_name IN ({})".format(
                ",".join("?" for _ in sectors)
            ),
            tuple(sectors),
        )
        codes = [row[0] for row in cursor.fetchall()]
        rows = []
        for code in codes:
            detail = xtdata.get_instrument_detail(code)
            if not detail:
                continue
            rows.append(
                (
                    code,
                    detail.get("InstrumentName"),
                    detail.get("ExchangeID"),
                    self._determine_board(code, detail),
                    detail.get("OpenDate"),
                    detail.get("TotalShares"),
                    detail.get("CirculatingShares"),
                )
            )
        spec = UpsertSpec(
            table="stock_basic",
            columns=(
                "stock_code",
                "stock_name",
                "market",
                "board",
                "listed_date",
                "total_volume",
                "float_volume",
            ),
            conflict_columns=("stock_code",),
        )
        updated = upsert_rows(self.conn, spec, rows, update_columns=(
            "stock_name",
            "market",
            "board",
            "listed_date",
            "total_volume",
            "float_volume",
        ))
        self.conn.commit()
        return updated

    def download_daily_for_codes(
        self,
        codes: Sequence[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        dividend_type: str = "back_ratio",
    ) -> int:
        total = 0
        start = to_yyyymmdd(start_date or "20080101")
        end = to_yyyymmdd(end_date) if end_date else ""
        iterable = (
            tqdm(
                codes,
                desc="xtquant daily",
                total=len(codes) if hasattr(codes, "__len__") else None,
                leave=False,
            )
            if tqdm
            else codes
        )
        for code in iterable:
            rows = self._download_single(code, start, end, dividend_type)
            if not rows:
                continue
            spec = UpsertSpec(
                table="daily_k_data",
                columns=(
                    "date",
                    "code",
                    "open",
                    "high",
                    "low",
                    "close",
                    "preclose",
                    "volume",
                    "amount",
                    "adjustflag",
                    "turn",
                    "tradestatus",
                    "pctChg",
                    "peTTM",
                    "pbMRQ",
                    "psTTM",
                    "pcfNcfTTM",
                    "isST",
                    "source",
                ),
                conflict_columns=("date", "code", "adjustflag"),
            )
            total += upsert_rows(
                self.conn,
                spec,
                rows,
                update_columns=(
                    "open",
                    "high",
                    "low",
                    "close",
                    "preclose",
                    "volume",
                    "amount",
                    "turn",
                    "tradestatus",
                    "pctChg",
                    "peTTM",
                    "pbMRQ",
                    "psTTM",
                    "pcfNcfTTM",
                    "isST",
                    "source",
                ),
            )
        self.conn.commit()
        return total

    def default_etf_codes(self) -> list[str]:
        cursor = self.conn.execute(
            "SELECT DISTINCT stock_code FROM sector_stocks WHERE sector_name = ?",
            ("沪深基金",),
        )
        return [row[0] for row in cursor.fetchall()]

    def _download_single(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
        dividend_type: str,
    ):
        start_dt = self._next_download_date(stock_code, start_date)
        try:
            xtdata.download_history_data(
                stock_code=stock_code,
                period="1d",
                start_time=start_dt,
                end_time=end_date,
                incrementally=True,
            )
            data = xtdata.get_market_data_ex(
                field_list=[
                    "time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "amount",
                    "preClose",
                    "turn",
                    "tradeStatus",
                    "pctChg",
                    "peTTM",
                    "pbMRQ",
                    "psTTM",
                    "pcfNcfTTM",
                    "isST",
                ],
                stock_list=[stock_code],
                period="1d",
                start_time=start_dt,
                end_time=end_date,
                dividend_type=dividend_type,
                fill_data=True,
            )
        except Exception as exc:  # pragma: no cover - network error path
            self.logger.warning("xtquant download failed for %s: %s", stock_code, exc)
            return []
        frame = data.get(stock_code) if data else None
        if frame is None or frame.empty:
            return []
        frame = frame.copy()
        index_series = frame.index.to_series()
        if not is_datetime64_any_dtype(index_series):
            index_series = pd.to_datetime(index_series, errors="coerce")
        if index_series.isna().all() and "time" in frame.columns:
            time_series = pd.to_datetime(frame["time"], errors="coerce")
            if time_series.isna().all():
                time_series = pd.to_datetime(frame["time"], unit="ms", errors="coerce")
            index_series = time_series
        mask = ~index_series.isna()
        frame = frame[mask].copy()
        index_series = index_series[mask]
        if frame.empty:
            return []
        frame["date"] = index_series.dt.strftime("%Y%m%d")
        frame["code"] = stock_code
        frame = frame.rename(columns={"preClose": "preclose", "tradeStatus": "tradestatus"})
        frame["adjustflag"] = 1
        frame["source"] = "xtquant"
        columns = [
            "date",
            "code",
            "open",
            "high",
            "low",
            "close",
            "preclose",
            "volume",
            "amount",
            "adjustflag",
            "turn",
            "tradestatus",
            "pctChg",
            "peTTM",
            "pbMRQ",
            "psTTM",
            "pcfNcfTTM",
            "isST",
            "source",
        ]
        for column in columns:
            if column not in frame.columns:
                frame[column] = None
        frame = frame[columns]
        return [tuple(row) for row in frame.itertuples(index=False, name=None)]

    def _determine_board(self, code: str, detail: dict) -> Optional[str]:
        if code.startswith("688"):
            return "科创板"
        if code.startswith("300"):
            return "创业板"
        if code.startswith("8"):
            return "北交所"
        return detail.get("InstrumentStatus")

    def _next_download_date(self, code: str, start_date: str) -> str:
        cursor = self.conn.execute(
            "SELECT MAX(date) FROM daily_k_data WHERE code=? AND adjustflag=1",
            (code,),
        )
        latest = cursor.fetchone()[0]
        if not latest:
            return start_date
        latest_dt = datetime.strptime(latest, "%Y%m%d") + timedelta(days=1)
        fallback = datetime.strptime(start_date, "%Y%m%d")
        return max(latest_dt, fallback).strftime("%Y%m%d")
