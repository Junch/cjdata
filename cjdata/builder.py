"""Orchestrates local database construction and updates."""
from __future__ import annotations

import logging
from typing import Optional, Sequence

from . import db
from .baostock_pipeline import BaostockPipeline
from .xtquant_pipeline import XtQuantPipeline

logger = logging.getLogger(__name__)


class CJDataBuilder:
    def __init__(self, db_path: str, logger_override: Optional[logging.Logger] = None) -> None:
        self.db_path = db_path
        self.logger = logger_override or logger

    def bootstrap(
        self,
        start_date: str = "20080101",
        end_date: Optional[str] = None,
        include_dupont: bool = False,
        skip_xtquant: bool = False,
        skip_baostock: bool = False,
    ) -> None:
        with db.connection(self.db_path) as conn:
            db.ensure_schema(conn)
            if not skip_xtquant:
                try:
                    xt_logger = self.logger.getChild("xtquant")
                    xt_pipeline = XtQuantPipeline(conn, xt_logger)
                    xt_pipeline.download_trading_calendar()
                    xt_pipeline.update_sector_membership()
                    xt_pipeline.update_stock_basic()
                    etf_codes = xt_pipeline.default_etf_codes()
                    if etf_codes:
                        xt_logger.info("Downloading ETF daily data for %s codes", len(etf_codes))
                        xt_pipeline.download_daily_for_codes(etf_codes, start_date=start_date, end_date=end_date)
                except RuntimeError as exc:
                    self.logger.warning("Skip xtquant stage: %s", exc)
            if not skip_baostock:
                try:
                    bs_logger = self.logger.getChild("baostock")
                    bs_pipeline = BaostockPipeline(conn, bs_logger)
                    codes = self._sector_codes(conn, ("沪深A股", "沪深指数"))
                    if codes:
                        bs_logger.info("Downloading BA daily data for %s codes", len(codes))
                        bs_pipeline.download_daily_for_codes(codes, start_date=start_date, end_date=end_date)
                    if include_dupont:
                        dupont_codes = self._sector_codes(conn, ("沪深A股",))
                        if dupont_codes:
                            bs_logger.info("Downloading DuPont data for %s codes", len(dupont_codes))
                            bs_pipeline.download_dupont_for_codes(dupont_codes)
                except RuntimeError as exc:
                    self.logger.warning("Skip baostock stage: %s", exc)

    def update(
        self,
        end_date: Optional[str] = None,
        skip_xtquant: bool = False,
        skip_baostock: bool = False,
    ) -> None:
        with db.connection(self.db_path) as conn:
            db.ensure_schema(conn)
            if not skip_xtquant:
                try:
                    xt_logger = self.logger.getChild("xtquant")
                    xt_pipeline = XtQuantPipeline(conn, xt_logger)
                    etf_codes = xt_pipeline.default_etf_codes()
                    if etf_codes:
                        xt_logger.info("Updating ETF daily data for %s codes", len(etf_codes))
                        xt_pipeline.download_daily_for_codes(etf_codes, end_date=end_date)
                except RuntimeError as exc:
                    self.logger.warning("Skip xtquant update: %s", exc)
            if not skip_baostock:
                try:
                    bs_logger = self.logger.getChild("baostock")
                    bs_pipeline = BaostockPipeline(conn, bs_logger)
                    codes = self._sector_codes(conn, ("沪深A股", "沪深指数"))
                    if codes:
                        bs_logger.info("Updating BA daily data for %s codes", len(codes))
                        bs_pipeline.download_daily_for_codes(codes, end_date=end_date)
                except RuntimeError as exc:
                    self.logger.warning("Skip baostock update: %s", exc)

    def _sector_codes(self, conn, sectors: Sequence[str]) -> list[str]:
        cursor = conn.execute(
            "SELECT DISTINCT stock_code FROM sector_stocks WHERE sector_name IN ({})".format(
                ",".join("?" for _ in sectors)
            ),
            tuple(sectors),
        )
        return [row[0] for row in cursor.fetchall()]
