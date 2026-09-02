"""pipeline.cli 테스트 — 네트워크에 나가지 않는다.

`sync_playwright`/`fetchers.monthly_fetchers`/`fetchers.series_fetchers`/
`collect.run_*` 를 전부 가짜로 갈아끼운다. 브라우저도 KOSIS 도 실제로
뜨지 않는다. `cli.ROOT` 를 tmp_path 로 몽키패치해 실제 저장소 `data/` 를
건드리지 않는다.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from pipeline import center_map, cli, collect, fetchers, series


def _freeze(monkeypatch, year, month, day=1):
    """`cli.date.today()` 가 고정된 날짜를 돌려주게 한다 (latest_month/halfyear 계산용)."""
    fixed = date(year, month, day)

    class _FixedDate(date):
        @classmethod
        def today(cls):
            return fixed

    monkeypatch.setattr(cli, "date", _FixedDate)


# ---------------------------------------------------------------------------
# latest_month — 연말 경계
# ---------------------------------------------------------------------------

def test_latest_month_is_two_months_before_today(monkeypatch):
    _freeze(monkeypatch, 2026, 9, 2)
    assert cli.latest_month() == "202607"


def test_latest_month_crosses_year_boundary_in_january(monkeypatch):
    """1월 실행 → 2개월 전은 전년도 11월이다."""
    _freeze(monkeypatch, 2026, 1, 15)
    assert cli.latest_month() == "202511"


def test_latest_month_crosses_year_boundary_in_february(monkeypatch):
    """2월 실행 → 2개월 전은 전년도 12월이다."""
    _freeze(monkeypatch, 2026, 2, 1)
    assert cli.latest_month() == "202512"


# ---------------------------------------------------------------------------
# 가짜 playwright — 브라우저를 실제로 띄우지 않는다.
# ---------------------------------------------------------------------------

class _FakeBrowser:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, browser):
        self._browser = browser

    def launch(self):
        return self._browser


class _FakeP:
    def __init__(self, browser):
        self.chromium = _FakeChromium(browser)


class _FakeSyncPlaywright:
    def __init__(self, browser):
        self._browser = browser

    def __enter__(self):
        return _FakeP(self._browser)

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_playwright(monkeypatch):
    browser = _FakeBrowser()
    monkeypatch.setattr(cli, "sync_playwright", lambda: _FakeSyncPlaywright(browser))
    return browser


# ---------------------------------------------------------------------------
# main("monthly")
# ---------------------------------------------------------------------------

def test_main_monthly_calls_run_monthly_with_latest_month(tmp_path, monkeypatch, fake_playwright):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    _freeze(monkeypatch, 2026, 9, 2)

    sentinel_cm = object()
    monkeypatch.setattr(center_map, "load", lambda path: sentinel_cm)

    calls = {}

    def fake_monthly_fetchers(*, browser, cm, **kwargs):
        calls["fetchers_browser"] = browser
        calls["fetchers_cm"] = cm
        return {"vacancy": lambda period: None}

    def fake_run_monthly(period, *, out_dir, fetchers, cm, previous=None):
        calls["run_monthly"] = dict(period=period, out_dir=out_dir,
                                     fetchers=fetchers, cm=cm, previous=previous)
        return {"vacancy": 1}

    monkeypatch.setattr(fetchers, "monthly_fetchers", fake_monthly_fetchers)
    monkeypatch.setattr(collect, "run_monthly", fake_run_monthly)

    result = cli.main("monthly")

    assert result == 0
    assert calls["run_monthly"]["period"] == "202607"          # latest_month()
    assert calls["run_monthly"]["out_dir"] == tmp_path / "data"
    assert calls["run_monthly"]["cm"] is sentinel_cm
    assert calls["run_monthly"]["previous"] == {}              # 아직 지난달 파일이 없다
    assert calls["fetchers_cm"] is sentinel_cm
    assert calls["fetchers_browser"] is fake_playwright
    assert fake_playwright.closed                               # 브라우저를 정리한다


def test_main_monthly_reads_previous_month_rows_for_check(tmp_path, monkeypatch, fake_playwright):
    """previous 는 run_monthly 의 check_not_identical_to_previous 가 곧바로
    rows 리스트와 비교하는 자리라(collect.py 주석), 파일에서 rows 만 뽑아 건넨다."""
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _freeze(monkeypatch, 2026, 9, 2)
    monkeypatch.setattr(center_map, "load", lambda path: object())

    prior_rows = [{"sigungu": "11110", "vacancy": 5}]
    (data_dir / "vacancy.json").write_text(
        json.dumps({"period": "202606", "rows": prior_rows}), encoding="utf-8")

    monkeypatch.setattr(fetchers, "monthly_fetchers",
                        lambda **kw: {"vacancy": lambda period: None})

    calls = {}
    monkeypatch.setattr(
        collect, "run_monthly",
        lambda period, *, out_dir, fetchers, cm, previous=None:
            calls.setdefault("previous", previous) and {"vacancy": 0})

    cli.main("monthly")

    assert calls["previous"] == {"vacancy": prior_rows}


# ---------------------------------------------------------------------------
# main("series")
# ---------------------------------------------------------------------------

def test_main_series_backfills_full_history_on_first_collection(tmp_path, monkeypatch, fake_playwright):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    (tmp_path / "data").mkdir()
    _freeze(monkeypatch, 2026, 9, 2)   # latest_month() -> 202607

    calls = {}

    def fake_series_fetchers(periods, *, browser, **kwargs):
        calls["periods"] = periods
        calls["browser"] = browser
        return {"vacancy_series": lambda: []}

    def fake_run_series(*, out_dir, fetchers, previous=None):
        calls["run_series"] = dict(out_dir=out_dir, fetchers=fetchers, previous=previous)
        return {"vacancy_series": 0}

    monkeypatch.setattr(fetchers, "series_fetchers", fake_series_fetchers)
    monkeypatch.setattr(collect, "run_series", fake_run_series)

    result = cli.main("series")

    assert result == 0
    assert len(calls["periods"]) == series.SERIES_MONTHS      # 첫 수집은 24개월
    assert calls["periods"][-1] == "202607"                    # latest_month() 까지
    assert calls["periods"] == sorted(calls["periods"])        # 오래된 순
    assert calls["run_series"]["previous"] == {}
    assert fake_playwright.closed


def test_main_series_only_fetches_months_missing_from_existing_files(
        tmp_path, monkeypatch, fake_playwright):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _freeze(monkeypatch, 2026, 9, 2)   # latest_month() -> 202607

    full = cli._series_full_months("202607")
    existing_rows = [{"period": p, "sido": "11", "vacancy": 1} for p in full[:-1]]  # 최신월만 빠짐
    (data_dir / "vacancy_series.json").write_text(
        json.dumps({"rows": existing_rows}), encoding="utf-8")
    (data_dir / "insured_series.json").write_text(
        json.dumps({"rows": existing_rows}), encoding="utf-8")

    calls = {}
    monkeypatch.setattr(fetchers, "series_fetchers",
                        lambda periods, **kw: calls.setdefault("periods", periods) or {})
    monkeypatch.setattr(collect, "run_series", lambda **kw: {})

    cli.main("series")

    assert calls["periods"] == ["202607"]                       # 있는 달은 다시 안 받는다


def test_main_series_skips_the_call_entirely_when_nothing_new(
        tmp_path, monkeypatch, fake_playwright):
    """periods=[] 로 run_series 를 부르면 fetchers._fetch_series 가
    SeriesBackfillError 를 낸다 — 이미 다 쌓여 있는 정상 상태를 cli 가
    빈 목록으로 부르는 실패로 만들면 안 된다."""
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _freeze(monkeypatch, 2026, 9, 2)

    full = cli._series_full_months("202607")
    rows = [{"period": p, "sido": "11", "vacancy": 1} for p in full]
    (data_dir / "vacancy_series.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    (data_dir / "insured_series.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")

    called = {"run_series": False}
    monkeypatch.setattr(
        collect, "run_series",
        lambda **kw: called.__setitem__("run_series", True) or {})

    result = cli.main("series")

    assert result == 0
    assert called["run_series"] is False


# ---------------------------------------------------------------------------
# main("halfyear")
# ---------------------------------------------------------------------------

def test_main_halfyear_passes_compare_names_from_vacancy_json(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setenv("KOSIS_API_KEY", "test-key")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _freeze(monkeypatch, 2026, 6, 25)   # 6월 -> 상반기(YYYY01)

    (data_dir / "vacancy.json").write_text(
        json.dumps({"rows": [{"occupation": "경영·행정·사무직"},
                              {"occupation": "보건·의료직"}]}),
        encoding="utf-8")

    calls = {}

    def fake_run_halfyear(period, *, out_dir, api_key, collector=None, compare_names=None):
        calls.update(period=period, out_dir=out_dir, api_key=api_key,
                      compare_names=compare_names)
        return {"est": 1}

    monkeypatch.setattr(collect, "run_halfyear", fake_run_halfyear)

    result = cli.main("halfyear")

    assert result == 0
    assert calls["period"] == "202601"
    assert calls["out_dir"] == data_dir
    assert calls["api_key"] == "test-key"
    assert calls["compare_names"] == {"경영·행정·사무직", "보건·의료직"}


def test_main_halfyear_skips_compare_names_and_logs_when_vacancy_missing(
        tmp_path, monkeypatch, capsys):
    """9c 리뷰 지적: 안전망이 조용히 안 걸리면 있으나 마나다 — 건너뛴다는 사실이
    로그에 남아야 한다."""
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setenv("KOSIS_API_KEY", "test-key")
    (tmp_path / "data").mkdir()
    _freeze(monkeypatch, 2026, 12, 25)   # 12월 -> 하반기(YYYY02)

    calls = {}
    monkeypatch.setattr(
        collect, "run_halfyear",
        lambda period, *, out_dir, api_key, collector=None, compare_names=None:
            calls.setdefault("compare_names", compare_names) and {"est": 1})

    cli.main("halfyear")

    assert calls.get("compare_names") is None
    assert "건너뛴다" in capsys.readouterr().out


def test_main_halfyear_dies_with_readable_message_when_api_key_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.delenv("KOSIS_API_KEY", raising=False)
    (tmp_path / "data").mkdir()

    with pytest.raises(SystemExit, match="KOSIS_API_KEY"):
        cli.main("halfyear")


# ---------------------------------------------------------------------------
# 모르는 모드
# ---------------------------------------------------------------------------

def test_main_unknown_mode_dies():
    with pytest.raises(SystemExit):
        cli.main("no-such-mode")
