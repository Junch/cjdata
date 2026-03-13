from __future__ import annotations

from contextlib import contextmanager

import pytest

import cjdata.builder as builder_module
import cjdata.cli as cli_module


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConn:
    def __init__(self):
        self.executed = []

    def execute(self, sql, params):
        self.executed.append((sql, tuple(params)))
        if tuple(params) == ("沪深A股", "沪深指数"):
            return _FakeCursor([("000001.SZ",), ("000300.SH",)])
        if tuple(params) == ("沪深A股",):
            return _FakeCursor([("000001.SZ",)])
        return _FakeCursor([])


class _RecordingBaostockPipeline:
    def __init__(self, conn, logger):
        self.conn = conn
        self.logger = logger
        self.daily_calls = []
        self.dupont_calls = []

    def download_daily_for_codes(self, codes, start_date=None, end_date=None):
        self.daily_calls.append((tuple(codes), start_date, end_date))

    def download_dupont_for_codes(self, codes, start_year=2007, start_quarter=1, start_date=None):
        self.dupont_calls.append((tuple(codes), start_year, start_quarter, start_date))


class _RecordingXtPipeline:
    def __init__(self, conn, logger):
        self.conn = conn
        self.logger = logger
        self.daily_calls = []

    def download_trading_calendar(self):
        return None

    def update_sector_membership(self):
        return None

    def update_stock_basic(self):
        return None

    def default_etf_codes(self):
        return ["510300.SH"]

    def download_daily_for_codes(self, codes, start_date=None, end_date=None):
        self.daily_calls.append((tuple(codes), start_date, end_date))


def _patch_builder_dependencies(monkeypatch):
    fake_conn = _FakeConn()
    created_bs = []
    created_xt = []

    @contextmanager
    def _fake_connection(_db_path):
        yield fake_conn

    def _fake_bs_factory(conn, logger):
        pipeline = _RecordingBaostockPipeline(conn, logger)
        created_bs.append(pipeline)
        return pipeline

    def _fake_xt_factory(conn, logger):
        pipeline = _RecordingXtPipeline(conn, logger)
        created_xt.append(pipeline)
        return pipeline

    monkeypatch.setattr(builder_module.db, "connection", _fake_connection)
    monkeypatch.setattr(builder_module.db, "ensure_schema", lambda conn: None)
    monkeypatch.setattr(builder_module, "BaostockPipeline", _fake_bs_factory)
    monkeypatch.setattr(builder_module, "XtQuantPipeline", _fake_xt_factory)
    return created_bs, created_xt


def test_bootstrap_runs_dupont_when_daily_skipped(monkeypatch):
    created_bs, _ = _patch_builder_dependencies(monkeypatch)

    builder = builder_module.CJDataBuilder("ignored.db")
    builder.bootstrap(skip_xtquant=True, skip_daily=True)

    assert len(created_bs) == 1
    assert created_bs[0].daily_calls == []
    assert created_bs[0].dupont_calls == [(("000001.SZ",), 2007, 1, "20080101")]


def test_update_skips_dupont_when_requested(monkeypatch):
    created_bs, _ = _patch_builder_dependencies(monkeypatch)

    builder = builder_module.CJDataBuilder("ignored.db")
    builder.update(skip_xtquant=True, skip_daily=True, skip_dupont=True)

    assert len(created_bs) == 1
    assert created_bs[0].daily_calls == []
    assert created_bs[0].dupont_calls == []


def test_update_runs_dupont_without_start_date(monkeypatch):
    created_bs, _ = _patch_builder_dependencies(monkeypatch)

    builder = builder_module.CJDataBuilder("ignored.db")
    builder.update(skip_xtquant=True, skip_daily=True)

    assert len(created_bs) == 1
    assert created_bs[0].dupont_calls == [(("000001.SZ",), 2007, 1, None)]


def test_parser_uses_skip_dupont_not_include_dupont():
    parser = cli_module.build_parser()

    args = parser.parse_args(["download", "--skip-dupont", "--skip-daily"])
    assert args.skip_dupont is True
    assert args.skip_daily is True

    args = parser.parse_args(["update", "--skip-dupont", "--skip-daily"])
    assert args.skip_dupont is True
    assert args.skip_daily is True

    args = parser.parse_args(["download", "--only-dupont"])
    assert args.only_dupont is True

    args = parser.parse_args(["update", "--only-dupont"])
    assert args.only_dupont is True


def test_cli_main_forwards_skip_flags(monkeypatch):
    captured = {}

    class _BuilderSpy:
        def __init__(self, db_path):
            captured["db_path"] = db_path

        def bootstrap(self, **kwargs):
            captured["bootstrap"] = kwargs

        def update(self, **kwargs):
            captured["update"] = kwargs

    monkeypatch.setattr(cli_module, "CJDataBuilder", _BuilderSpy)

    rc = cli_module.main(["download", "--db", "demo.db", "--skip-daily", "--skip-dupont"])
    assert rc == 0
    assert captured["db_path"] == "demo.db"
    assert captured["bootstrap"]["skip_daily"] is True
    assert captured["bootstrap"]["skip_dupont"] is True

    rc = cli_module.main(["update", "--db", "demo.db", "--skip-daily", "--skip-dupont"])
    assert rc == 0
    assert captured["update"]["skip_daily"] is True
    assert captured["update"]["skip_dupont"] is True


def test_download_allows_skip_xtquant_and_forwards(monkeypatch):
    captured = {}

    class _BuilderSpy:
        def __init__(self, _db_path):
            return None

        def bootstrap(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(cli_module, "CJDataBuilder", _BuilderSpy)

    rc = cli_module.main(["download", "--skip-xtquant"])
    assert rc == 0
    assert captured["skip_xtquant"] is True


def test_only_dupont_sets_skip_xtquant_and_skip_daily(monkeypatch):
    captured = {}

    class _BuilderSpy:
        def __init__(self, _db_path):
            return None

        def bootstrap(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(cli_module, "CJDataBuilder", _BuilderSpy)

    rc = cli_module.main(["download", "--only-dupont"])
    assert rc == 0
    assert captured["skip_xtquant"] is True
    assert captured["skip_daily"] is True
    assert captured["skip_dupont"] is False


def test_only_dupont_conflicts_with_skip_dupont():
    with pytest.raises(SystemExit):
        cli_module.main(["download", "--only-dupont", "--skip-dupont"])


def test_only_dupont_conflicts_with_skip_baostock():
    with pytest.raises(SystemExit):
        cli_module.main(["download", "--only-dupont", "--skip-baostock"])
