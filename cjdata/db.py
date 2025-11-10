"""SQLite schema helpers for the cjdata package."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable, Iterator, Sequence, Any, Optional

SCHEMA_STATEMENTS: tuple[str, ...] = (
    "PRAGMA foreign_keys = ON;",
    """
    CREATE TABLE IF NOT EXISTS stock_basic (
        stock_code TEXT PRIMARY KEY,
        stock_name TEXT,
        market TEXT,
        board TEXT,
        listed_date TEXT,
        total_volume REAL,
        float_volume REAL,
        updated_at TEXT DEFAULT (strftime('%Y%m%d%H%M%S', 'now', 'localtime'))
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_k_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        code TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        preclose REAL,
        volume REAL,
        amount REAL,
        adjustflag INTEGER NOT NULL,
        turn REAL,
        tradestatus INTEGER,
        pctChg REAL,
        peTTM REAL,
        pbMRQ REAL,
        psTTM REAL,
        pcfNcfTTM REAL,
        isST INTEGER,
        source TEXT,
        created_at TEXT DEFAULT (strftime('%Y%m%d%H%M%S', 'now', 'localtime')),
        UNIQUE(date, code, adjustflag)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS sector_stocks (
        sector_name TEXT NOT NULL,
        stock_code TEXT NOT NULL,
        PRIMARY KEY (sector_name, stock_code)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trading_days (
        market TEXT NOT NULL,
        trade_date INTEGER NOT NULL,
        PRIMARY KEY (market, trade_date)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS dupont_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL,
        pubDate TEXT NOT NULL,
        statDate TEXT NOT NULL,
        dupontROE REAL,
        dupontAssetStoEquity REAL,
        dupontAssetTurn REAL,
        dupontPnitoni REAL,
        dupontNitogr REAL,
        dupontTaxBurden REAL,
        dupontIntburden REAL,
        dupontEbittogr REAL,
        UNIQUE(code, statDate)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS minutes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_code TEXT NOT NULL,
        freq TEXT NOT NULL,
        trade_time TEXT,
        time INTEGER NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL,
        amount REAL,
        pre_close REAL,
        UNIQUE(stock_code, freq, time)
    );
    """,
)


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def connection(path: str) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def ensure_schema(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    for statement in SCHEMA_STATEMENTS:
        cursor.executescript(statement)
    cursor.close()
    conn.commit()


@dataclass(frozen=True)
class UpsertSpec:
    table: str
    columns: Sequence[str]
    conflict_columns: Sequence[str]


def upsert_rows(
    conn: sqlite3.Connection,
    spec: UpsertSpec,
    rows: Iterable[Sequence[Any]],
    update_columns: Optional[Sequence[str]] = None,
) -> int:
    rows = list(rows)
    if not rows:
        return 0

    placeholders = ", ".join(["?" for _ in spec.columns])
    column_list = ", ".join(spec.columns)

    if update_columns is None:
        sql = (
            f"INSERT OR IGNORE INTO {spec.table} ({column_list}) "
            f"VALUES ({placeholders})"
        )
    else:
        update_clause = ", ".join(
            f"{col}=excluded.{col}" for col in update_columns
        )
        conflict_cols = ", ".join(spec.conflict_columns)
        sql = (
            f"INSERT INTO {spec.table} ({column_list}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict_cols}) DO UPDATE SET {update_clause}"
        )

    conn.executemany(sql, rows)
    return len(rows)


def insert_ignore(
    conn: sqlite3.Connection,
    table: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
) -> int:
    rows = list(rows)
    if not rows:
        return 0
    placeholders = ", ".join(["?" for _ in columns])
    column_list = ", ".join(columns)
    sql = (
        f"INSERT OR IGNORE INTO {table} ({column_list}) VALUES ({placeholders})"
    )
    conn.executemany(sql, rows)
    return len(rows)


def delete_rows(
    conn: sqlite3.Connection,
    table: str,
    where_clause: str,
    params: Sequence[Any],
) -> None:
    sql = f"DELETE FROM {table} WHERE {where_clause}"
    conn.execute(sql, params)
