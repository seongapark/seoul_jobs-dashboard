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


def _sido_parts(rows, field):
    """시군구 행을 시도별로 더한다 (테스트가 시도 값을 맞추는 데 쓴다)."""
    out = {}
    for row in rows:
        out[row["sigungu"][:2]] = out.get(row["sigungu"][:2], 0) + row[field]
    return out


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

def test_dual_era_incheon_rows_are_accepted(tmp_path):
    """R50 — 옛·신 인천 코드가 같은 달에 함께 오는 것은 **정상**이다.

    실측(2026-09-02): 인천 시군구를 전부 더하고 시도 잔여를 얹어야 시도 값과
    정확히 맞는다(9,268/86,627). 신설 코드만 쓰면 구인 159·구직 7,968 이
    사라진다 — 두 시대는 상호배타이고 옛 코드 값은 미이관분이다. 그래서 예전에
    이 조합을 막던 check_incheon_codes 를 지웠고, 이제 70개가 다 오면 통과한다."""
    rows = [{"period": "202607", "sigungu": code, "center": CM.center_of(code),
             "vacancy": 1, "seekers": 1} for code in CM.codes()]  # 진짜 70개, 두 era 다 포함
    fetchers = {"vacancy": lambda period: Fetched(rows, {"vacancy": 70, "seekers": 70})}

    summary = collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)

    assert summary["vacancy"] == 70


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

def test_writes_nothing_when_metro_parts_exceed_the_national_total(tmp_path):
    """R46 — 수도권 분해합이 전국 총계를 넘으면 실패한다.

    이 방향이 잡아야 하는 실패는 페이지 중복으로 행이 이중계상되거나 자릿수
    파싱이 깨지는 것 — R47 이 실제로 잡은 바로 그런 종류다."""
    too_small_totals = {"vacancy": 10 * len(_REALISTIC_CODES) - 1,
                        "seekers": 100 * len(_REALISTIC_CODES)}
    fetchers = {"vacancy": lambda period: Fetched(_full_rows(period), too_small_totals)}
    with pytest.raises(checks.CheckFailed):
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert not list(tmp_path.iterdir())


def test_parts_below_the_total_pass_because_the_grid_total_is_nationwide(tmp_path):
    """R46 — 분해합이 총계보다 작은 것은 **정상**이다.

    그리드 총계 행은 전국이고 `지역무관`·시도 잔여 멤버까지 포함하는데 우리는
    수도권만 받는다(실측). 옛 equality/at_least 계약은 이 경우를 실패로 봤고,
    그래서 실데이터로는 영원히 통과할 수 없었다. 누락 방향은 여기가 아니라
    시군구 70개 완전성 검사가 잡는다 — 두 검사가 양방향을 함께 덮는다."""
    nationwide_totals = {"vacancy": 10 * len(_REALISTIC_CODES) * 5,
                         "seekers": 100 * len(_REALISTIC_CODES) * 5}
    fetchers = {"vacancy": lambda period: Fetched(_full_rows(period), nationwide_totals)}
    summary = collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert summary["vacancy"] == len(_REALISTIC_CODES)


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
    # 시도 값이 시군구 합과 다른 것이 이 테스트의 요지다 — 그 차이는 잔여로 설명된다
    # (R54 검산은 시군구합 + 잔여 == 시도값 을 요구한다).
    rows = _full_rows()
    residuals = {sido: {"vacancy": 999 - _sido_parts(rows, "vacancy").get(sido, 0),
                        "seekers": 999 - _sido_parts(rows, "seekers").get(sido, 0)}
                 for sido in ("11", "41", "28")}
    fetchers = {
        "vacancy": lambda period: Fetched(rows, _full_totals(), residuals=residuals),
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
    rows = _full_rows()
    # 시도 파일에 서울만 있어도 시군구 완전성 검사는 시도 행에 걸리지 않는다.
    # (시도 파일 자체의 완전성은 아래 별도 테스트가 본다.)
    sido_rows = [{"period": "202607", "sido": sido, "vacancy": 5, "seekers": 5}
                 for sido in ("11", "41", "28")]
    residuals = {sido: {"vacancy": 5 - _sido_parts(rows, "vacancy").get(sido, 0),
                        "seekers": 5 - _sido_parts(rows, "seekers").get(sido, 0)}
                 for sido in ("11", "41", "28")}
    fetchers = {
        "vacancy": lambda period: Fetched(rows, _full_totals(), residuals=residuals),
        "vacancy_sido": lambda period: Fetched(sido_rows, None),
    }
    summary = collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert summary["vacancy_sido"] == 3


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


# ---------------------------------------------------------------------------
# R40 — run_halfyear 가 이름 겹침 검사를 실제로 부르는지. compare_names 를
# 안 주면 조용히 건너뛴다(R18 이 이미 지적한 "배선 없는 죽은 검사" 실수를
# 반복하지 않기 위해, 준 경우엔 반드시 불러야 한다).
# ---------------------------------------------------------------------------

def _halfyear_rows_with_names():
    return [
        {"period": "202601", "sido": "11", "size": "전규모",
         "occupation": "02", "occupation_name": "경영·행정·사무직",
         "item": "채용계획인원", "value": 100},
    ]


def test_run_halfyear_skips_name_overlap_check_when_not_given(tmp_path):
    """compare_names 를 안 주면 검사를 건너뛴다 — est.py 만 단독으로 돌 때(비교 대상이
    없을 때)도 run_halfyear 가 죽으면 안 된다."""
    def collector(periods, api_key):
        return _halfyear_rows_with_names()

    summary = collect.run_halfyear("202601", out_dir=tmp_path, api_key="KEY", collector=collector)
    assert summary["est"] == 1


def test_run_halfyear_fails_when_compare_names_do_not_overlap(tmp_path):
    def collector(periods, api_key):
        return _halfyear_rows_with_names()

    with pytest.raises(checks.CheckFailed):
        collect.run_halfyear("202601", out_dir=tmp_path, api_key="KEY", collector=collector,
                              compare_names={"완전히 다른 이름"})
    assert not list(tmp_path.iterdir())  # 절반 갱신 금지 — 검사 실패 시 파일을 안 쓴다


def test_run_halfyear_passes_when_compare_names_overlap(tmp_path):
    def collector(periods, api_key):
        return _halfyear_rows_with_names()

    summary = collect.run_halfyear("202601", out_dir=tmp_path, api_key="KEY", collector=collector,
                                    compare_names={"경영·행정·사무직", "다른 이름"})
    assert summary["est"] == 1


# ---------------------------------------------------------------------------
# C2 — 산업별 표를 같은 함수로 한 번 더 받는다. 출력 파일명이 "est.json" 으로
# 못박혀 있으면 순진하게 두 번 부른 순간 두 번째가 첫 번째를 덮어쓴다.
# ---------------------------------------------------------------------------

def _halfyear_industry_rows():
    return [
        {"period": "202601", "sido": "11", "size": "전규모",
         "industry": "C", "industry_name": "제조업",
         "item": "채용인원", "value": 200},
    ]


def test_run_halfyear_writes_the_file_it_is_told_to(tmp_path):
    def collector(periods, api_key):
        return _halfyear_industry_rows()

    summary = collect.run_halfyear("202601", out_dir=tmp_path, api_key="KEY",
                                   collector=collector, out_name="est_industry")
    assert summary == {"est_industry": 1}
    assert (tmp_path / "est_industry.json").exists()
    assert not (tmp_path / "est.json").exists()


def test_two_run_halfyear_calls_do_not_clobber_each_other(tmp_path):
    """직종 표와 산업 표를 나란히 받는 실제 수집 경로의 모양 그대로."""
    collect.run_halfyear("202601", out_dir=tmp_path, api_key="KEY",
                         collector=lambda periods, api_key: _halfyear_rows_with_names())
    collect.run_halfyear("202601", out_dir=tmp_path, api_key="KEY",
                         collector=lambda periods, api_key: _halfyear_industry_rows(),
                         out_name="est_industry")

    occupation = json.loads((tmp_path / "est.json").read_text(encoding="utf-8"))
    industry = json.loads((tmp_path / "est_industry.json").read_text(encoding="utf-8"))
    assert occupation["rows"][0]["occupation_name"] == "경영·행정·사무직"
    assert industry["rows"][0]["industry_name"] == "제조업"


def test_run_halfyear_checks_industry_names_against_the_given_set(tmp_path):
    """산업 쪽에도 이름 겹침 검사가 걸린다 — 지금은 직종 이름만 검사했다."""
    with pytest.raises(checks.CheckFailed):
        collect.run_halfyear("202601", out_dir=tmp_path, api_key="KEY",
                             collector=lambda periods, api_key: _halfyear_industry_rows(),
                             out_name="est_industry",
                             compare_names={"전혀 다른 업종"})
    assert not list(tmp_path.iterdir())


# ---------------------------------------------------------------------------
# Task 15a — 산업 축 데이터셋(vacancy_industry/insured_industry)
# ---------------------------------------------------------------------------

def test_industry_axis_dataset_gets_the_same_checks_as_its_pair(tmp_path):
    """산업 축도 시군구 축이다 — 시군구 완전성·총계 검산을 똑같이 받아야 한다."""
    fetchers = {"vacancy_industry": lambda period: Fetched(_full_rows(period), _full_totals())}
    summary = collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert summary["vacancy_industry"] == len(_REALISTIC_CODES)
    assert (tmp_path / "vacancy_industry.json").exists()


def test_industry_axis_dataset_fails_when_sigungu_are_missing(tmp_path):
    fetchers = {"vacancy_industry": lambda period: Fetched(_full_rows(period)[:3], _full_totals())}
    with pytest.raises(checks.CheckFailed):
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert not list(tmp_path.iterdir())


def test_industry_axis_dataset_fails_without_totals(tmp_path):
    """R18 — 총계를 못 받았으면 지어내지 않고 실패한다."""
    fetchers = {"vacancy_industry": lambda period: Fetched(_full_rows(period), None)}
    with pytest.raises(checks.CheckFailed):
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)


def test_mobility_fails_when_a_metro_sido_is_missing(tmp_path):
    """리뷰 Important 4 — mobility 는 시군구 완전성도 총계 검산도 안 받는 유일한
    데이터셋이라 그물이 check_not_all_zero 하나뿐이었다(한 행만 살아남아도 통과).
    반쪽짜리 mobility.json 이 조용히 나가면 안 된다."""
    rows = [{"period": "202607", "sido": "11", "industry": "J", "prev_industry": "M",
             "movers": 10}]
    fetchers = {"mobility": lambda period: Fetched(rows, None)}
    with pytest.raises(checks.CheckFailed):
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert not list(tmp_path.iterdir())


def test_mobility_passes_when_all_three_metro_sido_are_present(tmp_path):
    rows = [{"period": "202607", "sido": sido, "industry": "J", "prev_industry": "M",
             "movers": 10} for sido in ("11", "41", "28")]
    fetchers = {"mobility": lambda period: Fetched(rows, None)}
    summary = collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert summary["mobility"] == 3


# --- R54: 시도 검산이 실제 수집 경로에서 돈다 (구현만 하고 안 부르는 일 금지) ----

def _sido_rows(vacancy_by_sido, seekers_by_sido):
    return [{"period": "202607", "sido": sido, "vacancy": vacancy_by_sido[sido],
             "seekers": seekers_by_sido[sido]} for sido in ("11", "41", "28")]


def _parts_by_sido(rows, field):
    out = {}
    for row in rows:
        out[row["sigungu"][:2]] = out.get(row["sigungu"][:2], 0) + row[field]
    return out


def test_sido_check_runs_in_run_monthly_and_catches_a_short_sido(tmp_path):
    """R54 — 시도 합이 시도 값에 못 미치면(경기 일반구를 버리던 상황) 잡는다."""
    rows = _full_rows()
    vacancy = _parts_by_sido(rows, "vacancy")
    seekers = _parts_by_sido(rows, "seekers")
    vacancy["41"] += 22289                       # 시도 파일에는 있는데 시군구에 없다
    fetchers = {
        "vacancy": lambda period: Fetched(rows, _full_totals(), residuals={}),
        "vacancy_sido": lambda period: Fetched(_sido_rows(vacancy, seekers), None),
    }
    with pytest.raises(checks.CheckFailed) as e:
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert "41" in str(e.value)
    assert not list(tmp_path.iterdir())


def test_sido_check_passes_when_parts_plus_residual_match(tmp_path):
    rows = _full_rows()
    vacancy = _parts_by_sido(rows, "vacancy")
    seekers = _parts_by_sido(rows, "seekers")
    seekers["11"] += 248729                      # 시도까지만 적힌 건 = 잔여
    residuals = {"11": {"vacancy": 0, "seekers": 248729}}
    fetchers = {
        "vacancy": lambda period: Fetched(rows, _full_totals(), residuals=residuals),
        "vacancy_sido": lambda period: Fetched(_sido_rows(vacancy, seekers), None),
    }
    summary = collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert summary["vacancy"] == len(_REALISTIC_CODES)


def test_sido_check_is_skipped_when_the_pair_was_not_collected(tmp_path):
    """짝이 되는 시도 데이터셋이 이번 수집에 없으면 검산할 상대가 없다."""
    fetchers = {"vacancy": lambda period: Fetched(_full_rows(), _full_totals(), residuals={})}
    summary = collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert summary["vacancy"] == len(_REALISTIC_CODES)


def test_missing_residuals_is_a_failure_not_a_skip(tmp_path):
    """재리뷰 3 — residuals=None 을 '건너뜀'으로 다루면 가장 강한 그물이 조용히
    꺼진다. totals=None(R18)과 같은 논리로 그 자체를 실패로 본다."""
    fetchers = {
        "vacancy": lambda period: Fetched(_full_rows(period), _full_totals()),  # residuals 없음
        "vacancy_sido": lambda period: Fetched(
            [{"period": period, "sido": s, "vacancy": 5, "seekers": 5}
             for s in ("11", "41", "28")], None),
    }
    with pytest.raises(checks.CheckFailed) as e:
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert "residuals" in str(e.value)
    assert not list(tmp_path.iterdir())


def test_sido_file_missing_a_metro_sido_fails(tmp_path):
    """재리뷰 2 — check_sido_totals 는 시도 파일 행만 순회하므로, 인천 행이 통째로
    빠지면 인천이 검산에서 조용히 사라진다. 시도 파일 자체의 완전성을 요구한다."""
    rows = _full_rows()
    sido_rows = [{"period": "202607", "sido": s, "vacancy": 5, "seekers": 5}
                 for s in ("11", "41")]                      # 인천이 없다
    residuals = {s: {"vacancy": 5 - _sido_parts(rows, "vacancy").get(s, 0),
                     "seekers": 5 - _sido_parts(rows, "seekers").get(s, 0)}
                 for s in ("11", "41", "28")}
    fetchers = {
        "vacancy": lambda period: Fetched(rows, _full_totals(), residuals=residuals),
        "vacancy_sido": lambda period: Fetched(sido_rows, None),
    }
    with pytest.raises(checks.CheckFailed) as e:
        collect.run_monthly("202607", out_dir=tmp_path, fetchers=fetchers, cm=CM)
    assert "28" in str(e.value)
