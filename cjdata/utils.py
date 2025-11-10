"""Utility helpers for cjdata."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Iterator, Sequence, TypeVar

T = TypeVar("T")


def to_yyyymmdd(date_str: str) -> str:
    if len(date_str) == 8 and date_str.isdigit():
        return date_str
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y%m%d")


def to_iso_date(date_str: str) -> str:
    if len(date_str) == 10 and date_str[4] == "-":
        return date_str
    return datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")


def chunked(seq: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    if size <= 0:
        raise ValueError("size must be > 0")
    for idx in range(0, len(seq), size):
        yield seq[idx : idx + size]


def ensure_list(iterable: Iterable[T]) -> list[T]:
    return list(iterable)
