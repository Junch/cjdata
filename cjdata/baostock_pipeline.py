"""Data acquisition routines backed by baostock."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional, Sequence, Any

import pandas as pd

from .db import UpsertSpec, upsert_rows
from .utils import to_iso_date, to_yyyymmdd

try:  # pragma: no cover - optional dependency
    from tqdm import tqdm  # type: ignore
except ImportError:  # pragma: no cover
    tqdm = None  # type: ignore

bs: Any
try:  # pragma: no cover - optional dependency
    import baostock as bs  # type: ignore
except ImportError:  # pragma: no cover
    bs = None  # type: ignore

_LOGGER = logging.getLogger(__name__)


def _require_baostock() -> None:
    if bs is None:  # pragma: no cover
        raise RuntimeError("baostock is not installed. Install baostock to use this feature.")


@contextmanager
def _baostock_session() -> Iterator[Any]:
    _require_baostock()
    login_result = bs.login()
    if login_result.error_code != "0":  # pragma: no cover
        raise RuntimeError(f"baostock login failed: {login_result.error_msg}")
    try:
        yield bs
    finally:
        bs.logout()


def _to_baostock_code(code: str) -> str:
    if "." not in code:
        raise ValueError(f"invalid stock code: {code}")
    number, market = code.split(".")
    return f"{market.lower()}.{number}"


def _from_baostock_code(code: str) -> str:
    market, number = code.split(".")
    return f"{number}.{market.upper()}"


class BaostockPipeline:
    def __init__(self, conn, logger: Optional[logging.Logger] = None) -> None:
        _require_baostock()
        self.conn = conn
        self.logger = logger or _LOGGER

    def download_daily_for_codes(
        self,
        codes: Sequence[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjustflag: str = "1",
    ) -> int:
        start = to_yyyymmdd(start_date or "20080101")
        end = to_yyyymmdd(end_date) if end_date else None
        total = 0
        with _baostock_session() as session:
            iterable = (
                tqdm(
                    codes,
                    desc="baostock daily",
                    total=len(codes) if hasattr(codes, "__len__") else None,
                    leave=False,
                )
                if tqdm
                else codes
            )
            for code in iterable:
                rows = self._download_single_daily(session, code, start, end, adjustflag)
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

    def download_dupont_for_codes(
        self,
        codes: Sequence[str],
        start_year: int = 2007,
        start_quarter: int = 1,
    ) -> int:
        total = 0
        with _baostock_session() as session:
            for code in codes:
                total += self._download_single_dupont(session, code, start_year, start_quarter)
        self.conn.commit()
        return total

    def _download_single_daily(
        self,
        session: Any,
        stock_code: str,
        start_date: str,
        end_date: Optional[str],
        adjustflag: str,
    ) -> list[tuple[Any, ...]]:
        final_start = max(start_date, self._next_download_date(stock_code, adjustflag))
        start_iso = to_iso_date(final_start)
        end_iso = to_iso_date(end_date) if end_date else ""
        bs_code = _to_baostock_code(stock_code)
        try:
            rs = session.query_history_k_data_plus(
                code=bs_code,
                fields="date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST",
                start_date=start_iso,
                end_date=end_iso,
                frequency="d",
                adjustflag=adjustflag,
            )
        except Exception as exc:  # pragma: no cover - network errors
            self.logger.warning("baostock download failed for %s: %s", stock_code, exc)
            return []
        if rs.error_code != "0":  # pragma: no cover
            self.logger.warning("baostock error for %s: %s", stock_code, rs.error_msg)
            return []
        records = []
        while rs.next():
            records.append(rs.get_row_data())
        if not records:
            return []
        frame = pd.DataFrame(records, columns=rs.fields)
        frame["date"] = frame["date"].str.replace("-", "")
        frame["code"] = frame["code"].apply(_from_baostock_code)
        numeric_columns = [
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
        ]
        for column in numeric_columns:
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame["adjustflag"] = pd.to_numeric(frame["adjustflag"], errors="coerce").fillna(int(adjustflag)).astype(int)
        frame["source"] = "baostock"
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
        frame = frame[columns]
        return [tuple(row) for row in frame.itertuples(index=False, name=None)]

    def _download_single_dupont(
        self,
        session: Any,
        stock_code: str,
        start_year: int,
        start_quarter: int,
    ) -> int:
        bs_code = _to_baostock_code(stock_code)
        last_date = self._latest_dupont_quarter(stock_code)
        if last_date:
            year = int(last_date[:4])
            month = int(last_date[4:6])
            quarter = (month - 1) // 3 + 1
            start_year = year
            start_quarter = quarter + 1 if quarter < 4 else 1
            if quarter == 4:
                start_year = year + 1
        current = pd.Timestamp.now()
        total = 0
        for year in range(start_year, current.year + 1):
            first_quarter = start_quarter if year == start_year else 1
            last_quarter = ((current.month - 1) // 3 + 1) if year == current.year else 4
            for quarter in range(first_quarter, last_quarter + 1):
                try:
                    rs = session.query_dupont_data(code=bs_code, year=year, quarter=quarter)
                except Exception as exc:  # pragma: no cover
                    self.logger.warning("dupont download failed for %s %sQ%s: %s", stock_code, year, quarter, exc)
                    continue
                if rs.error_code != "0":  # pragma: no cover
                    if "no records" not in rs.error_msg.lower():
                        self.logger.warning("dupont error for %s %sQ%s: %s", stock_code, year, quarter, rs.error_msg)
                    continue
                records: list[dict[str, Any]] = []
                while rs.next():
                    records.append(dict(zip(rs.fields, rs.get_row_data())))
                if not records:
                    continue
                frame = pd.DataFrame(records)
                frame["code"] = frame["code"].apply(_from_baostock_code)
                frame["pubDate"] = frame["pubDate"].str.replace("-", "")
                frame["statDate"] = frame["statDate"].str.replace("-", "")
                numeric_columns = [
                    "dupontROE",
                    "dupontAssetStoEquity",
                    "dupontAssetTurn",
                    "dupontPnitoni",
                    "dupontNitogr",
                    "dupontTaxBurden",
                    "dupontIntburden",
                    "dupontEbittogr",
                ]
                for column in numeric_columns:
                    if column in frame.columns:
                        frame[column] = pd.to_numeric(frame[column], errors="coerce")
                spec = UpsertSpec(
                    table="dupont_data",
                    columns=tuple(frame.columns),
                    conflict_columns=("code", "statDate"),
                )
                total += upsert_rows(
                    self.conn,
                    spec,
                    [tuple(row) for row in frame.itertuples(index=False, name=None)],
                    update_columns=tuple(frame.columns),
                )
        return total

    def _next_download_date(self, code: str, adjustflag: str) -> str:
        cursor = self.conn.execute(
            "SELECT MAX(date) FROM daily_k_data WHERE code=? AND adjustflag=?",
            (code, int(adjustflag)),
        )
        latest = cursor.fetchone()[0]
        if not latest:
            return "20080101"
        latest_dt = datetime.strptime(latest, "%Y%m%d")
        next_dt = latest_dt + pd.Timedelta(days=1)
        return next_dt.strftime("%Y%m%d")

    def _latest_dupont_quarter(self, code: str) -> Optional[str]:
        cursor = self.conn.execute(
            "SELECT MAX(statDate) FROM dupont_data WHERE code=?",
            (code,),
        )
        value = cursor.fetchone()[0]
        return value if value else None
