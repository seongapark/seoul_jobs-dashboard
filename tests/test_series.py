"""pipeline.series 테스트 — 마감년월 축(시도 x 마감년월) 시계열, 네트워크 없음.

Task 9b brief(task-9b-brief.md) Step 1 테스트를 그대로 담는다. 유효구인구직
리포트의 기본 레이아웃은 (지역별)시도 x 마감년월이다(Task 6 실측) — 그래서
시계열은 축을 드래그로 옮기지 않고 기본 레이아웃 그대로 받아 24개월을 한
번에 백필한다(R27). §4.1 카드 2(24개월 추세)·§4.2 카드 8·§4.3 카드 11(6개월
평균)이 이 이력을 읽는다(R19).

기간 표기는 기존 fixture 관례(tests/fixtures/eis_vacancy_rows.json 등)를
따라 "2026년 07월" 형태로 둔다 — pipeline.eis.period_code 가 이미 그 형태를
파싱하고, Task 6/7 실측 fixture 도 전부 이 표기다. 브리프 예시 문장의
"마감년월": "202607" 은 변환 후 결과(period 필드)를 보여준 것으로 읽었다.
"""
import json
from pathlib import Path

import pytest

from pipeline import checks, collect, eis, series

ROOT = Path(__file__).resolve().parents[1]
VACANCY_FIXTURE = ROOT / "tests/fixtures/eis_vacancy_series_rows.json"
INSURED_FIXTURE = ROOT / "tests/fixtures/eis_insured_series_rows.json"


def _vacancy_row(period, sido, vacancy="1", seekers="1"):
    return {"마감년월": period, "(지역별)시도": sido,
            "유효구인인원(전체)": vacancy, "유효구직자수(전체)": seekers}


def _insured_row(period, sido, insured="1"):
    return {"마감년월": period, "(사업장)시도": sido, "피보험자수(전체)": insured}


def _months(n, start_year=2024, start_month=1):
    """start_year/start_month 부터 n개월 연속 "YYYY년 MM월" 문자열."""
    out = []
    y, m = start_year, start_month
    for _ in range(n):
        out.append(f"{y}년 {m:02d}월")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


# ---------------------------------------------------------------------------
# 브리프 Step 1, 단언 1~2 — collect_vacancy_series
# ---------------------------------------------------------------------------

def test_collect_vacancy_series_shapes_rows():
    rows = [
        _vacancy_row("2026년 07월", "서울", "48,120", "712,400"),
        _vacancy_row("2026년 06월", "경기", "50,000", "600,000"),
        _vacancy_row("2026년 05월", "인천", "10,000", "90,000"),
        _vacancy_row("2026년 07월", "총계", "165,821", "1,550,154"),
    ]
    out = series.collect_vacancy_series(rows)

    assert {tuple(sorted(r.keys())) for r in out} == {tuple(sorted(("period", "sido", "vacancy", "seekers")))}
    by_key = {(r["sido"], r["period"]): r for r in out}
    assert by_key[("11", "202607")]["vacancy"] == 48120
    assert by_key[("11", "202607")]["seekers"] == 712400
    assert by_key[("41", "202606")]["vacancy"] == 50000
    assert by_key[("28", "202605")]["seekers"] == 90000
    assert by_key[("00", "202607")]["vacancy"] == 165821


def test_collect_vacancy_series_rejects_unknown_sido():
    """지역 이름이 매핑에 없으면 조용히 버리지 않고 eis.UnknownRegion 을 그대로 올린다."""
    rows = [_vacancy_row("2026년 07월", "부산", "1", "1")]
    with pytest.raises(eis.UnknownRegion):
        series.collect_vacancy_series(rows)


# ---------------------------------------------------------------------------
# 브리프 Step 1, 단언 3 — collect_insured_series
# ---------------------------------------------------------------------------

def test_collect_insured_series_shapes_rows():
    rows = [
        _insured_row("2026년 07월", "서울", "4,698,520"),
        _insured_row("2026년 06월", "경기", "3,000,000"),
        _insured_row("2026년 07월", "총계", "9,000,000"),
    ]
    out = series.collect_insured_series(rows)

    assert {tuple(sorted(r.keys())) for r in out} == {("insured", "period", "sido")}
    by_key = {(r["sido"], r["period"]): r for r in out}
    assert by_key[("11", "202607")]["insured"] == 4698520
    assert by_key[("41", "202606")]["insured"] == 3000000
    assert by_key[("00", "202607")]["insured"] == 9000000


# ---------------------------------------------------------------------------
# 브리프 Step 1, 단언 4 — check_series_shape: (sido, period) 중복 금지
# ---------------------------------------------------------------------------

def test_check_series_shape_rejects_duplicate_sido_period():
    rows = [{"period": "202607", "sido": "11", "vacancy": 1},
            {"period": "202607", "sido": "11", "vacancy": 2}]
    with pytest.raises(checks.CheckFailed):
        checks.check_series_shape(rows)


def test_check_series_shape_passes_distinct_sido_period_pairs():
    rows = [{"period": "202607", "sido": "11"}, {"period": "202606", "sido": "11"},
            {"period": "202607", "sido": "41"}]
    checks.check_series_shape(rows)  # 예외 없음


# ---------------------------------------------------------------------------
# 브리프 Step 1, 단언 5 — check_series_shape: period 는 YYYYMM 6자리 숫자여야 한다
# (R19 를 기계로 못 박는 자리 — 합산된 "합계" 같은 기간 행이 섞이면 화면이
# 그것을 한 달인 양 선으로 잇는다)
# ---------------------------------------------------------------------------

def test_check_series_shape_rejects_non_numeric_period():
    rows = [{"period": "합계", "sido": "11"}]
    with pytest.raises(checks.CheckFailed):
        checks.check_series_shape(rows)


def test_check_series_shape_rejects_period_with_wrong_length():
    rows = [{"period": "2026", "sido": "11"}]
    with pytest.raises(checks.CheckFailed):
        checks.check_series_shape(rows)


# ---------------------------------------------------------------------------
# 브리프 Step 1, 단언 6 — check_series_months: 최소 관측월 미달
# ---------------------------------------------------------------------------

def test_check_series_months_rejects_when_below_minimum():
    rows = [{"period": "202607", "sido": "11"}]
    with pytest.raises(checks.CheckFailed):
        checks.check_series_months(rows, minimum=2)


def test_check_series_months_passes_when_meeting_minimum():
    rows = [{"period": "202607", "sido": "11"}, {"period": "202606", "sido": "11"}]
    checks.check_series_months(rows, minimum=2)


def test_check_series_months_checks_each_sido_independently():
    """한 시도가 기준을 채워도 다른 시도가 모자라면 실패한다."""
    rows = [{"period": "202607", "sido": "11"}, {"period": "202606", "sido": "11"},
            {"period": "202607", "sido": "41"}]
    with pytest.raises(checks.CheckFailed):
        checks.check_series_months(rows, minimum=2)


# ---------------------------------------------------------------------------
# 브리프 Step 1, 단언 7 — run_series: 검사를 다 통과한 뒤에야 쓴다
# ---------------------------------------------------------------------------

def _good_series_rows():
    return [{"period": "202607", "sido": "11", "vacancy": 1},
            {"period": "202606", "sido": "11", "vacancy": 2}]


def test_run_series_writes_files_after_checks_pass(tmp_path):
    fetchers = {"vacancy_series": lambda: _good_series_rows(),
                "insured_series": lambda: _good_series_rows()}
    summary = collect.run_series(out_dir=tmp_path, fetchers=fetchers)

    written = json.loads((tmp_path / "vacancy_series.json").read_text(encoding="utf-8"))
    assert written["rows"] == _good_series_rows()
    assert "collected_at" in written
    assert (tmp_path / "insured_series.json").exists()
    assert summary == {"vacancy_series": 2, "insured_series": 2}


def test_run_series_writes_nothing_when_a_check_fails(tmp_path):
    """절반만 갱신된 상태를 만들지 않는다 — 하나라도 실패하면 아무 파일도 안 쓴다."""
    bad_rows = [{"period": "202607", "sido": "11", "vacancy": 1}]  # 1개월뿐
    fetchers = {"vacancy_series": lambda: _good_series_rows(),
                "insured_series": lambda: bad_rows}
    with pytest.raises(checks.CheckFailed):
        collect.run_series(out_dir=tmp_path, fetchers=fetchers)
    assert not list(tmp_path.iterdir())


def test_run_series_does_not_touch_network(monkeypatch, tmp_path):
    import requests

    def boom(*a, **k):
        raise AssertionError("테스트가 네트워크에 나갔다")

    monkeypatch.setattr(requests, "get", boom)
    fetchers = {"vacancy_series": lambda: _good_series_rows(),
                "insured_series": lambda: _good_series_rows()}
    collect.run_series(out_dir=tmp_path, fetchers=fetchers)


# ---------------------------------------------------------------------------
# 브리프 Step 1, 단언 8 — SERIES_MONTHS = 24 상한 (시도별로 최근 24개월만)
# ---------------------------------------------------------------------------

def test_series_months_cap_is_24():
    assert series.SERIES_MONTHS == 24


def test_collect_vacancy_series_keeps_only_most_recent_24_months_per_sido():
    rows = [_vacancy_row(month, "서울") for month in _months(25)]  # 25개월치, 서울만
    out = series.collect_vacancy_series(rows)

    assert len(out) == 24
    periods = sorted(r["period"] for r in out)
    assert periods[0] == "202402"   # 가장 오래된 202401 은 버려진다
    assert periods[-1] == "202601"


def test_collect_vacancy_series_caps_each_sido_independently():
    """25개월 서울 + 3개월 경기 — 경기는 상한에 안 걸려 3개월 그대로 남는다."""
    rows = ([_vacancy_row(month, "서울") for month in _months(25)]
            + [_vacancy_row(month, "경기") for month in _months(3, start_year=2026, start_month=5)])
    out = series.collect_vacancy_series(rows)

    by_sido: dict[str, list[dict]] = {}
    for row in out:
        by_sido.setdefault(row["sido"], []).append(row)
    assert len(by_sido["11"]) == 24
    assert len(by_sido["41"]) == 3


def test_collect_insured_series_keeps_only_most_recent_24_months_per_sido():
    rows = [_insured_row(month, "인천") for month in _months(25)]
    out = series.collect_insured_series(rows)
    assert len(out) == 24


# ---------------------------------------------------------------------------
# 손으로 구성한 구조 검증용 표본 — 시도별(서울/경기/인천/총계) 3개월치.
# 실뷰어 캡처 여부는 Step 4 실측 결과에 따라 fixture 의 _source 에 적는다.
# ---------------------------------------------------------------------------

def test_collect_vacancy_series_over_sample_fixture():
    payload = json.loads(VACANCY_FIXTURE.read_text(encoding="utf-8"))
    out = series.collect_vacancy_series(payload["rows"])

    checks.check_series_shape(out)
    checks.check_series_months(out, minimum=2)
    assert {"00", "11", "28", "41"} <= {r["sido"] for r in out}


def test_collect_insured_series_over_sample_fixture():
    payload = json.loads(INSURED_FIXTURE.read_text(encoding="utf-8"))
    out = series.collect_insured_series(payload["rows"])

    checks.check_series_shape(out)
    checks.check_series_months(out, minimum=2)
    assert {"00", "11", "28", "41"} <= {r["sido"] for r in out}


# ---------------------------------------------------------------------------
# R39 — run_series 는 previous 를 덮어쓰지 않고 병합한다.
#
# R34 실측으로 "한 그리드로 24개월"이 성립하지 않는다는 게 드러났다 — EIS
# 는 closYm 이 가리키는 한 달치만 준다. 그래서 시계열은 달마다 한 조각씩
# 받아 쌓는 방식(R39)으로 바뀌었고, run_series 는 새로 받은 조각을 지난번
# 파일(previous)에 병합해야 한다 — 덮어쓰면 이력이 통째로 날아간다(R19가
# 막으려던 바로 그 실패).
# ---------------------------------------------------------------------------

def _period_range(n, start_year=2024, start_month=1):
    """start_year/start_month 부터 n개월 연속 "YYYYMM" 문자열 (series 행 값 그대로)."""
    out = []
    y, m = start_year, start_month
    for _ in range(n):
        out.append(f"{y}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def test_run_series_merges_new_month_onto_previous_history(tmp_path):
    """지난달 파일(202605~202607) + 새 달(202608) = 4개월, 옛 달이 살아 있다."""
    previous_rows = [{"period": p, "sido": "11", "vacancy": 1}
                      for p in ("202605", "202606", "202607")]
    new_rows = [{"period": "202608", "sido": "11", "vacancy": 2}]
    previous = {"vacancy_series": {"rows": previous_rows}}
    fetchers = {"vacancy_series": lambda: new_rows}

    collect.run_series(out_dir=tmp_path, fetchers=fetchers, previous=previous)

    written = json.loads((tmp_path / "vacancy_series.json").read_text(encoding="utf-8"))
    periods = sorted(r["period"] for r in written["rows"])
    assert periods == ["202605", "202606", "202607", "202608"]


def test_run_series_new_value_wins_on_overlapping_key(tmp_path):
    """같은 (sido, period) 가 겹치면 새로 받은 값이 이긴다 — 확정치 정정 대응.

    check_series_months(minimum=2 기본값)를 만족시키려고 겹치지 않는
    달(202606)을 하나 더 둔다 — 이 테스트가 보려는 건 202607 하나의 덮어
    쓰기 여부일 뿐이다.
    """
    previous_rows = [{"period": "202606", "sido": "11", "vacancy": 5},
                      {"period": "202607", "sido": "11", "vacancy": 999}]
    new_rows = [{"period": "202607", "sido": "11", "vacancy": 42}]
    previous = {"vacancy_series": {"rows": previous_rows}}
    fetchers = {"vacancy_series": lambda: new_rows}

    collect.run_series(out_dir=tmp_path, fetchers=fetchers, previous=previous)

    written = json.loads((tmp_path / "vacancy_series.json").read_text(encoding="utf-8"))
    assert len(written["rows"]) == 2
    by_period = {r["period"]: r for r in written["rows"]}
    assert by_period["202607"]["vacancy"] == 42
    assert by_period["202606"]["vacancy"] == 5


def test_run_series_caps_to_24_months_after_merging_not_before(tmp_path):
    """옛 3개월 + 새 22개월 = 25개월 — 병합 뒤에야 24개월로 잘린다(옛 것에만 걸지 않는다)."""
    old_periods = _period_range(3, start_year=2024, start_month=1)     # 202401~202403
    new_periods = _period_range(22, start_year=2024, start_month=4)    # 202404~202601
    previous_rows = [{"period": p, "sido": "11", "vacancy": 1} for p in old_periods]
    new_rows = [{"period": p, "sido": "11", "vacancy": 2} for p in new_periods]
    previous = {"vacancy_series": {"rows": previous_rows}}
    fetchers = {"vacancy_series": lambda: new_rows}

    collect.run_series(out_dir=tmp_path, fetchers=fetchers, previous=previous)

    written = json.loads((tmp_path / "vacancy_series.json").read_text(encoding="utf-8"))
    periods = sorted(r["period"] for r in written["rows"])
    assert len(periods) == 24
    assert old_periods[0] not in periods   # 202401 은 가장 오래됐으니 잘린다
    assert new_periods[-1] in periods      # 가장 최근은 남는다


def test_run_series_without_previous_behaves_like_first_collection(tmp_path):
    """previous=None(첫 수집)이면 지금까지의 동작 그대로다."""
    fetchers = {"vacancy_series": lambda: _good_series_rows(),
                "insured_series": lambda: _good_series_rows()}
    summary = collect.run_series(out_dir=tmp_path, fetchers=fetchers, previous=None)
    assert summary == {"vacancy_series": 2, "insured_series": 2}
