"""Orchestrates local database construction and updates."""
from __future__ import annotations

import logging
from typing import Optional, Sequence

from . import db
from .baostock_pipeline import BaostockPipeline
from .xtquant_pipeline import XtQuantPipeline

logger = logging.getLogger(__name__)

SMOKE_TEST_LIMIT = 5


class CJDataBuilder:
    def __init__(self, db_path: str, logger_override: Optional[logging.Logger] = None) -> None:
        self.db_path = db_path
        self.logger = logger_override or logger

    def bootstrap(
        self,
        start_date: str = "20080101",
        end_date: Optional[str] = None,
        skip_xtquant: bool = False,
        skip_baostock: bool = False,
        skip_daily: bool = False,
        skip_dupont: bool = False,
        smoke_test: bool = False,
    ) -> None:
        with db.connection(self.db_path) as conn:
            db.ensure_schema(conn)
            self.logger.info("=== Bootstrap started (db=%s) ===", self.db_path)
            if not skip_xtquant:
                try:
                    xt_logger = self.logger.getChild("xtquant")
                    xt_pipeline = XtQuantPipeline(conn, xt_logger)
                    xt_logger.info("Downloading trading calendar")
                    xt_pipeline.download_trading_calendar()
                    xt_logger.info("Updating sector membership")
                    xt_pipeline.update_sector_membership()
                    xt_logger.info("Updating stock basic info")
                    xt_pipeline.update_stock_basic()
                    etf_codes = xt_pipeline.default_etf_codes()
                    if etf_codes:
                        if smoke_test:
                            etf_codes = etf_codes[:SMOKE_TEST_LIMIT]
                        if not skip_daily:
                            xt_logger.info("Downloading ETF daily data for %s codes", len(etf_codes))
                            xt_pipeline.download_daily_for_codes(etf_codes, start_date=start_date, end_date=end_date)
                            xt_logger.info("ETF daily data done")
                        else:
                            xt_logger.info("ETF daily data skipped")
                    else:
                        xt_logger.info("No ETF codes found, skipping ETF daily download")
                except RuntimeError as exc:
                    self.logger.warning("Skip xtquant stage: %s", exc)
            else:
                self.logger.info("xtquant stage skipped")
            if not skip_baostock:
                try:
                    bs_logger = self.logger.getChild("baostock")
                    bs_pipeline = BaostockPipeline(conn, bs_logger)
                    codes = self._sector_codes(conn, ("沪深A股", "沪深指数"))
                    if smoke_test:
                        codes = codes[:SMOKE_TEST_LIMIT]
                    if skip_daily:
                        bs_logger.info("Daily data skipped")
                    else:
                        if codes:
                            bs_logger.info("Downloading daily data for %s codes", len(codes))
                            bs_pipeline.download_daily_for_codes(codes, start_date=start_date, end_date=end_date)
                            bs_logger.info("Daily data done")
                        else:
                            bs_logger.info("No codes found for daily download")
                    if not skip_dupont:
                        dupont_codes = self._sector_codes(conn, ("沪深A股",))
                        if smoke_test:
                            dupont_codes = dupont_codes[:SMOKE_TEST_LIMIT]
                        if dupont_codes:
                            bs_logger.info("Downloading DuPont data for %s codes", len(dupont_codes))
                            bs_pipeline.download_dupont_for_codes(dupont_codes, start_date=start_date)
                            bs_logger.info("DuPont data done")
                        else:
                            bs_logger.info("No codes found for DuPont download")
                    else:
                        bs_logger.info("DuPont data skipped")
                except RuntimeError as exc:
                    self.logger.warning("Skip baostock stage: %s", exc)
            else:
                self.logger.info("baostock stage skipped")
            self.logger.info("=== Bootstrap completed ===")

    def update(
        self,
        end_date: Optional[str] = None,
        skip_xtquant: bool = False,
        skip_baostock: bool = False,
        skip_daily: bool = False,
        skip_dupont: bool = False,
        smoke_test: bool = False,
    ) -> None:
        with db.connection(self.db_path) as conn:
            db.ensure_schema(conn)
            self.logger.info("=== Update started (db=%s) ===", self.db_path)
            if not skip_xtquant:
                try:
                    xt_logger = self.logger.getChild("xtquant")
                    xt_pipeline = XtQuantPipeline(conn, xt_logger)
                    xt_logger.info("Updating sector membership")
                    xt_pipeline.update_sector_membership()
                    xt_logger.info("Updating stock basic info")
                    xt_pipeline.update_stock_basic()
                    etf_codes = xt_pipeline.default_etf_codes()
                    if etf_codes:
                        if smoke_test:
                            etf_codes = etf_codes[:SMOKE_TEST_LIMIT]
                        if not skip_daily:
                            xt_logger.info("Updating ETF daily data for %s codes", len(etf_codes))
                            xt_pipeline.download_daily_for_codes(etf_codes, end_date=end_date)
                            xt_logger.info("ETF daily data done")
                        else:
                            xt_logger.info("ETF daily data skipped")
                    else:
                        xt_logger.info("No ETF codes found, skipping ETF daily update")
                except RuntimeError as exc:
                    self.logger.warning("Skip xtquant update: %s", exc)
            else:
                self.logger.info("xtquant stage skipped")
            if not skip_baostock:
                try:
                    bs_logger = self.logger.getChild("baostock")
                    bs_pipeline = BaostockPipeline(conn, bs_logger)
                    codes = self._sector_codes(conn, ("沪深A股", "沪深指数"))
                    if smoke_test:
                        codes = codes[:SMOKE_TEST_LIMIT]
                    if skip_daily:
                        bs_logger.info("Daily data skipped")
                    else:
                        if codes:
                            bs_logger.info("Updating daily data for %s codes", len(codes))
                            bs_pipeline.download_daily_for_codes(codes, end_date=end_date)
                            bs_logger.info("Daily data done")
                        else:
                            bs_logger.info("No codes found for daily update")
                    if not skip_dupont:
                        dupont_codes = self._sector_codes(conn, ("沪深A股",))
                        if smoke_test:
                            dupont_codes = dupont_codes[:SMOKE_TEST_LIMIT]
                        if dupont_codes:
                            bs_logger.info("Updating DuPont data for %s codes", len(dupont_codes))
                            bs_pipeline.download_dupont_for_codes(dupont_codes)
                            bs_logger.info("DuPont data done")
                        else:
                            bs_logger.info("No codes found for DuPont update")
                    else:
                        bs_logger.info("DuPont data skipped")
                except RuntimeError as exc:
                    self.logger.warning("Skip baostock update: %s", exc)
            else:
                self.logger.info("baostock stage skipped")
            self.logger.info("=== Update completed ===")

    def _sector_codes(self, conn, sectors: Sequence[str]) -> list[str]:
        cursor = conn.execute(
            "SELECT DISTINCT stock_code FROM sector_stocks WHERE sector_name IN ({})".format(
                ",".join("?" for _ in sectors)
            ),
            tuple(sectors),
        )
        return [row[0] for row in cursor.fetchall()]
