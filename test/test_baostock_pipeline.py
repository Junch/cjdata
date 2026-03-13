from __future__ import annotations

from contextlib import contextmanager
import logging

import pytest

import cjdata.baostock_pipeline as baostock_pipeline
from cjdata.baostock_pipeline import _dupont_start_from_date


def test_dupont_start_from_q1_moves_to_previous_year_q4():
    assert _dupont_start_from_date("2024-01-15") == (2023, 4)


def test_dupont_start_from_q2_moves_to_q1():
    assert _dupont_start_from_date("20240420") == (2024, 1)


def test_dupont_start_from_q3_moves_to_q2():
    assert _dupont_start_from_date("2024-09-01") == (2024, 2)


def test_dupont_start_from_q4_moves_to_q3():
    assert _dupont_start_from_date("20241231") == (2024, 3)


class _FakeConn:
    def __init__(self) -> None:
        self.commit_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1


def _build_pipeline(conn: _FakeConn):
    pipeline = baostock_pipeline.BaostockPipeline.__new__(baostock_pipeline.BaostockPipeline)
    pipeline.conn = conn
    pipeline.logger = logging.getLogger("test.baostock")
    return pipeline


def test_dupont_commits_after_each_code(monkeypatch):
    conn = _FakeConn()
    pipeline = _build_pipeline(conn)

    @contextmanager
    def _fake_session():
        yield object()

    monkeypatch.setattr(baostock_pipeline, "_baostock_session", _fake_session)
    monkeypatch.setattr(
        pipeline,
        "_download_single_dupont",
        lambda _session, _code, _year, _quarter: 1,
    )

    total = pipeline.download_dupont_for_codes(["000001.SZ", "000300.SH"])

    assert total == 2
    assert conn.commit_calls == 2


def test_dupont_keeps_previous_commits_when_later_code_fails(monkeypatch):
    conn = _FakeConn()
    pipeline = _build_pipeline(conn)

    @contextmanager
    def _fake_session():
        yield object()

    monkeypatch.setattr(baostock_pipeline, "_baostock_session", _fake_session)

    def _fake_download(_session, code, _year, _quarter):
        if code == "000300.SH":
            raise RuntimeError("stop")
        return 1

    monkeypatch.setattr(pipeline, "_download_single_dupont", _fake_download)

    with pytest.raises(RuntimeError, match="stop"):
        pipeline.download_dupont_for_codes(["000001.SZ", "000300.SH"])

    assert conn.commit_calls == 1
