import json
from pathlib import Path
import pytest
from pipeline import collect, checks, center_map
from pipeline.collect import Fetched

ROOT = Path(__file__).resolve().parents[1]
CM = center_map.load(ROOT / "data/center_map.json")

# center_map.json 은 인천 개편 전후 코드(28110/28140/28260 옛 → 28125/28155/
# 28275/28290 신설)를 과거 자료 색인용으로 "영구히" 함께 보존한다 — 그래서
# CM.codes() 70개는 실제로는 절대 동시에 다 나올 수 없는 두 era 의 합집합
# 이다(둘이 함께 나오면 check_incheon_codes 가 바로 실패시킨다). 브리프
# 원안의 _full_rows 는 CM.codes() 전체(70개)를 그대로 쓰는데, 그건 이
# 저장소의 실제 center_map.json 으로는 절대 만들 수 없는 데이터다 — 만들면
# check_incheon_codes 가 (정당하게) 막는다. 그래서 여기서는 "한 달에 실제로
# 나올 수 있는 최대 커버리지"인 옛 코드 3개를 뺀 67개를 "완전"으로 삼는다
# (지금은 2026-09, 개편 이후라 신설 코드만 나온다). collect.py 의
# _effective_expected_codes 가 바로 이 옛/신 어느 한쪽만 요구하는 완화를
# 한다 — 그 완화가 없으면 매달 수집이 영구히 실패한다.
_OLD_INCHEON_CODES = set(checks.INCHEON_OLD_TO_NEW.keys())
_REALISTIC_CODES = sorted(CM.codes() - _OLD_INCHEON_CODES)  # 67개, 신설 코드만


def _full_rows(period="202607"):
    return [{"period": period, "sigungu": code, "center": CM.center_of(code),
             "occupation": "02", "industry": "J 정보통신업",
             "vacancy": 10, "seekers": 100} for code in _REALISTIC_CODES]


def _full_totals():
    """_full_rows() 와 정확히 맞아떨어지는 총계 — vacancy=equality, seekers=at_least."""
    return {"vacancy": 10 * len(_REALISTIC_CODES), "seekers": 100 * len(_REALISTIC_CODES)}


def test_writes_files_when_checks_pass(tmp_path):
    fetchers = {"vacancy": lambda period: Fetched(_full_rows(period), _full_totals())}
    summary = collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    written = json.loads((tmp_path / "vacancy.json").read_text(encoding="utf-8"))
    assert written["period"] == "202607"
    assert len(written["rows"]) == len(_REALISTIC_CODES)
    assert summary["vacancy"] == len(_REALISTIC_CODES)


def test_writes_nothing_when_a_check_fails(tmp_path):
    """검사가 실패하면 기존 데이터를 건드리지 않는다 — 절반만 갱신되는 상태가 최악이다."""
    fetchers = {"vacancy": lambda period: Fetched(_full_rows(period)[:3], _full_totals())}
    with pytest.raises(checks.CheckFailed):
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert not list(tmp_path.iterdir())


def test_does_not_touch_network(monkeypatch, tmp_path):
    import requests

    def boom(*a, **k):
        raise AssertionError("테스트가 네트워크에 나갔다")

    monkeypatch.setattr(requests, "get", boom)
    fetchers = {"vacancy": lambda period: Fetched(_full_rows(period), _full_totals())}
    collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)


# --- 완전성 검사의 인천 개편 인지(era-aware) ------------------------------------

def test_dual_era_incheon_rows_still_fail_even_though_70_is_complete(tmp_path):
    """CM.codes() 그대로 70개를 다 채우면 check_regions 만 보면 '완전'하지만,
    그 70개 자체가 개편 전후 코드를 동시에 담고 있으므로 check_incheon_codes
    가 잡아야 한다 — run_monthly 는 두 검사를 다 거친다."""
    rows = [{"period": "202607", "sigungu": code, "center": CM.center_of(code),
             "vacancy": 1, "seekers": 1} for code in CM.codes()]  # 진짜 70개, 두 era 다 포함
    fetchers = {"vacancy": lambda period: Fetched(rows, {"vacancy": 70, "seekers": 70})}
    with pytest.raises(checks.CheckFailed):
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert not list(tmp_path.iterdir())


def test_missing_region_still_fails_when_neither_era_present(tmp_path):
    """옛 코드도 신설 코드도 전혀 없는 인천 개편 그룹은 여전히 '빠졌다'로 잡아야 한다
    — era 완화가 '아무 근거 없이' 요구를 없애 주면 안 된다."""
    rows = [r for r in _full_rows() if r["sigungu"] not in ("28125", "28155")]  # 제물포·영종 통째로 누락
    fetchers = {"vacancy": lambda period: Fetched(rows, _full_totals())}
    with pytest.raises(checks.CheckFailed):
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert not list(tmp_path.iterdir())


# --- R18: check_against_total 을 실제 경로에서 강제한다 --------------------------
#
# R13 에서 만든 check_against_total 이 애초엔 run_monthly 에서 호출되지 않아
# 죽은 코드였다 — 그리드 총계 행이 시군구 합과 어긋나도 아무도 못 잡았다.
# 이제 fetcher 는 rows 뿐 아니라 totals({필드: 총계})를 함께 돌려주고,
# run_monthly 가 시군구 검사 대상 데이터셋(vacancy/placement/insured)마다
# 그 총계를 실제로 검산한다.

def test_writes_nothing_when_total_mismatches(tmp_path):
    """유효구인인원은 equality — 그리드 총계가 시군구 합과 다르면 아무것도 안 쓴다."""
    wrong_totals = {"vacancy": 10 * len(_REALISTIC_CODES) + 1, "seekers": 100 * len(_REALISTIC_CODES)}
    fetchers = {"vacancy": lambda period: Fetched(_full_rows(period), wrong_totals)}
    with pytest.raises(checks.CheckFailed):
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert not list(tmp_path.iterdir())


def test_writes_nothing_when_seekers_total_undershoots(tmp_path):
    """유효구직건수는 at_least — 시군구 합이 총계에 못 미치면(행 소실) 실패."""
    too_high_seekers_total = {"vacancy": 10 * len(_REALISTIC_CODES),
                               "seekers": 100 * len(_REALISTIC_CODES) + 1}
    fetchers = {"vacancy": lambda period: Fetched(_full_rows(period), too_high_seekers_total)}
    with pytest.raises(checks.CheckFailed):
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert not list(tmp_path.iterdir())


def test_writes_nothing_when_total_is_missing_for_a_checked_dataset(tmp_path):
    """총계가 있어야 하는 데이터셋이 totals=None 으로 오면 그 자체가 실패다 —
    '총계가 없으니 조용히 통과'는 선택지가 아니다(그리드 모양이 바뀌어 총계
    파싱이 조용히 깨졌다는 신호일 수 있다)."""
    fetchers = {"vacancy": lambda period: Fetched(_full_rows(period), None)}
    with pytest.raises(checks.CheckFailed):
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert not list(tmp_path.iterdir())


# --- R4: 시도 파일은 따로 -----------------------------------------------------
#
# 시도 총계는 시군구 합이 아니라 EIS 의 별도 _sido 리포트에서 그대로 받는다
# (유효구직건수는 1인 다건이라 시군구 합이 시도 총계보다 커질 수 있다 —
# checks.check_against_total 이 그 관계를 검산하지, run_monthly 가 시군구를
# 더해 시도 값을 만들지는 않는다). fetchers 에 "<name>_sido" 키로 넣은
# 콜백의 결과는 시군구 검사(완전성·인천 코드·총계 검산)를 건너뛰고 그대로
# "<name>_sido.json" 에 쓴다 — totals 는 굳이 필요 없어 None 으로 둔다.

def test_writes_sido_file_from_separate_collector_not_summed(tmp_path):
    sido_rows = [
        {"period": "202607", "sido": "11", "vacancy": 999, "seekers": 999},
        {"period": "202607", "sido": "41", "vacancy": 999, "seekers": 999},
        {"period": "202607", "sido": "28", "vacancy": 999, "seekers": 999},
        {"period": "202607", "sido": "00", "vacancy": 999, "seekers": 999},
    ]
    fetchers = {
        "vacancy": lambda period: Fetched(_full_rows(period), _full_totals()),
        "vacancy_sido": lambda period: Fetched(sido_rows, None),
    }
    summary = collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)

    written = json.loads((tmp_path / "vacancy_sido.json").read_text(encoding="utf-8"))
    assert written["rows"] == sido_rows  # 시군구 합(67*10=670)이 아니라 별도 값 그대로
    assert summary["vacancy_sido"] == 4
    # 시군구 파일도 여전히 별도로 쓰여 있다 — 시도 파일이 대체하지 않는다.
    assert (tmp_path / "vacancy.json").exists()


def test_sido_rows_skip_region_completeness_check(tmp_path):
    """시도 행은 시군구 완전성 검사 대상이 아니다 — 애초에 시군구가 아니다."""
    fetchers = {
        "vacancy": lambda period: Fetched(_full_rows(period), _full_totals()),
        "vacancy_sido": lambda period: Fetched(
            [{"period": period, "sido": "11", "vacancy": 5, "seekers": 5}], None),
    }
    summary = collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert summary["vacancy_sido"] == 1


def test_writes_nothing_when_sido_check_fails(tmp_path):
    """시도 값이 전부 0이면(수집 실패) 시군구 파일도 함께 안 쓴다 — 절반 갱신 금지는 시도에도 적용."""
    fetchers = {
        "vacancy": lambda period: Fetched(_full_rows(period), _full_totals()),
        "vacancy_sido": lambda period: Fetched(
            [{"period": period, "sido": "11", "vacancy": 0, "seekers": 0}], None),
    }
    with pytest.raises(checks.CheckFailed):
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert not list(tmp_path.iterdir())
