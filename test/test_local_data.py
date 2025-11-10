"""Tests for LocalData read-only access."""
import os
import pytest
import pandas as pd
from cjdata.local_data import LocalData, CodeFormat


@pytest.fixture
def db_path():
    """Provide the path to the test database."""
    return os.path.join(os.path.dirname(__file__), "..", "data", "stock_data_hfq.db")


@pytest.fixture
def local_data(db_path):
    """Create a LocalData instance for testing."""
    if not os.path.exists(db_path):
        pytest.skip(f"Test database not found at {db_path}")
    data = LocalData(db_path)
    yield data
    data.close()


def test_connection(local_data):
    """Verify database connection is established."""
    assert local_data.conn is not None


def test_get_latest_date(local_data):
    """Check that get_latest_date returns a valid date string."""
    latest = local_data.get_latest_date()
    if latest:
        assert len(latest) == 8
        assert latest.isdigit()


def test_get_stock_name(local_data):
    """Test retrieving stock name by code."""
    # Try a common stock code (adjust if your DB has different data)
    name = local_data.get_stock_name("000001.SZ")
    # Allow empty string if stock doesn't exist in DB
    assert isinstance(name, str)


def test_get_daily_data(local_data):
    """Test fetching daily K-line data."""
    # Use a plausible date range and stock code
    df = local_data.get_daily("000001.SZ", "20240101", "20240131", adj="hfq")
    assert isinstance(df, pd.DataFrame)
    # If data exists, check columns
    if not df.empty:
        assert "open" in df.columns
        assert "close" in df.columns
        assert df.index.name == "trade_date" or "trade_date" in df.columns


def test_get_weekly_data(local_data):
    """Test resampling daily data to weekly."""
    df = local_data.get_weekly("000001.SZ", "20240101", "20240331", adj="qfq")
    assert isinstance(df, pd.DataFrame)
    if not df.empty:
        assert "close" in df.columns


def test_get_price(local_data):
    """Test retrieving closing price for a specific date."""
    price = local_data.get_price("000001.SZ", "20240131", adj="qfq")
    assert isinstance(price, float)
    assert price >= 0.0


def test_search_stocks(local_data):
    """Test searching for stocks by code or name."""
    results = local_data.search_stocks("000001", limit=5)
    assert isinstance(results, list)
    for code, name in results:
        assert isinstance(code, str)
        assert isinstance(name, str)


def test_get_stock_list_in_sector(local_data):
    """Test retrieving stock codes within a sector."""
    codes = local_data.get_stock_list_in_sector("沪深A股", format=CodeFormat.MARKET_SUFFIX)
    assert isinstance(codes, list)
    # Allow empty if sector doesn't exist
    for code in codes:
        assert isinstance(code, str)


def test_get_etf_sector_list(local_data):
    """Test retrieving list of ETF sectors."""
    sectors = local_data.get_etf_sector_list()
    assert isinstance(sectors, list)
    for sector in sectors:
        assert isinstance(sector, str)
        assert sector.startswith("ETF")


def test_get_trading_dates(local_data):
    """Test retrieving trading calendar dates."""
    df = local_data.get_trading_dates("SH", "2024-01-01", "2024-01-31")
    assert isinstance(df, pd.DataFrame)
    if not df.empty:
        assert "trade_date" in df.columns


def test_table_exists(local_data):
    """Test internal table existence check."""
    # daily_k_data should exist if DB is populated
    exists = local_data._table_exists("daily_k_data")
    assert isinstance(exists, bool)
