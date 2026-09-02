from pathlib import Path
import pytest
from pipeline import checks, center_map

CM = center_map.load(Path(__file__).resolve().parents[1] / "data/center_map.json")


def _row(sigungu, vacancy=1, period="202607"):
    return {"period": period, "sigungu": sigungu, "center": CM.center_of(sigungu),
            "vacancy": vacancy, "seekers": 10}


def test_missing_region_fails():
    rows = [_row("11680")]
    with pytest.raises(checks.CheckFailed) as e:
        checks.check_regions(rows, CM)
    assert "69" in str(e.value)  # 69개가 비었다


def test_all_regions_passes():
    checks.check_regions([_row(code) for code in CM.codes()], CM)


def test_all_zero_fails():
    rows = [_row(code, vacancy=0) for code in CM.codes()]
    with pytest.raises(checks.CheckFailed):
        checks.check_not_all_zero(rows, "vacancy")


def test_identical_to_previous_month_fails():
    """같은 값이 그대로 다시 오면 수집이 실제로는 안 된 것이다."""
    rows = [_row(code) for code in CM.codes()]
    with pytest.raises(checks.CheckFailed):
        checks.check_not_identical_to_previous(rows, list(rows))


def test_incheon_old_and_new_codes_in_same_month_fail():
    """중구(28110)와 제물포구(28125)가 같은 달에 함께 값을 가지면 더해질 위험이 있다."""
    rows = [_row("28110"), _row("28125")]
    with pytest.raises(checks.CheckFailed) as e:
        checks.check_incheon_codes(rows)
    assert "28125" in str(e.value)


def test_incheon_new_codes_alone_pass():
    checks.check_incheon_codes([_row("28125"), _row("28155")])


def test_est_seam_jump_fails():
    """표가 갈리는 경계에서 값이 3배 튀면 코드 매핑이 어긋난 것이다."""
    rows = [{"period": "202502", "occupation": "02", "item": "채용계획인원", "value": 27139},
            {"period": "202601", "occupation": "02", "item": "채용계획인원", "value": 90000}]
    with pytest.raises(checks.CheckFailed):
        checks.check_est_seam(rows)


def test_est_seam_normal_change_passes():
    rows = [{"period": "202502", "occupation": "02", "item": "채용계획인원", "value": 27139},
            {"period": "202601", "occupation": "02", "item": "채용계획인원", "value": 26828}]
    checks.check_est_seam(rows)


# --- R13: 총계 행을 실제 검산으로 쓴다 ---------------------------------------
#
# 유효구인인원은 등치(==)로, 유효구직건수는 이상(>=)으로 검사한다. 그 비대칭이
# 이 파일에서 가장 헷갈리기 쉬운 규칙이라 여기 다시 적는다:
#   - 구인은 "건" 하나에 근무지역 하나 — 시군구 합은 총계와 정확히 같아야
#     한다. 다르면 행이 소실됐거나 이중계상됐다는 뜻이다.
#   - 구직은 "건" 하나가 희망근무지역을 여럿 낼 수 있다(1인 다건/다지역) —
#     그래서 시군구 합이 총계보다 커지는 것이 정상이다. 합이 총계에 못
#     미치면 그건 정상적인 초과가 아니라 행이 빠졌다는 뜻이다.


def test_check_against_total_equality_passes_when_equal():
    rows = [{"sigungu": "11110", "vacancy": 5}, {"sigungu": "11140", "vacancy": 7}]
    total = {"vacancy": 12}
    checks.check_against_total(rows, total, field="vacancy", mode="equality")


def test_check_against_total_equality_fails_when_over():
    rows = [{"sigungu": "11110", "vacancy": 5}, {"sigungu": "11140", "vacancy": 8}]
    total = {"vacancy": 12}
    with pytest.raises(checks.CheckFailed):
        checks.check_against_total(rows, total, field="vacancy", mode="equality")


def test_check_against_total_equality_fails_when_under():
    rows = [{"sigungu": "11110", "vacancy": 5}, {"sigungu": "11140", "vacancy": 6}]
    total = {"vacancy": 12}
    with pytest.raises(checks.CheckFailed):
        checks.check_against_total(rows, total, field="vacancy", mode="equality")


def test_check_against_total_at_least_passes_when_over():
    """구직건은 1건이 여러 희망근무지역을 낼 수 있어 합이 총계를 넘는 게 정상이다."""
    rows = [{"sigungu": "11110", "seekers": 8}, {"sigungu": "11140", "seekers": 7}]
    total = {"seekers": 12}
    checks.check_against_total(rows, total, field="seekers", mode="at_least")


def test_check_against_total_at_least_passes_when_equal():
    rows = [{"sigungu": "11110", "seekers": 6}, {"sigungu": "11140", "seekers": 6}]
    total = {"seekers": 12}
    checks.check_against_total(rows, total, field="seekers", mode="at_least")


def test_check_against_total_at_least_fails_when_under():
    """합이 총계에 못 미치면 초과가 아니라 소실이다."""
    rows = [{"sigungu": "11110", "seekers": 3}, {"sigungu": "11140", "seekers": 4}]
    total = {"seekers": 12}
    with pytest.raises(checks.CheckFailed):
        checks.check_against_total(rows, total, field="seekers", mode="at_least")


# --- Fix round 1: 인천 개편 era 완화(pipeline.collect._effective_expected_codes)
#     가 진짜로 새는 구멍이 아닌지 실측으로 고정한다 --------------------------------
#
# 그 완화 로직 자체는 pipeline/collect.py 에 있다(run_monthly 가 raw cm.codes()
# 70개 대신, 관측된 인천 era 만 요구하도록 기대 코드 집합을 조정해 checks.
# check_regions 에 넘긴다). 여기서는 조정된 기대 집합을 check_regions 에 직접
# 먹여, "완화가 인천 밖으로 새지 않는다"는 것을 checks 모듈 레벨에서도 증명한다.
from pipeline import collect  # noqa: E402

_OLD_INCHEON_CODES = set(checks.INCHEON_OLD_TO_NEW.keys())
_REALISTIC_CODES = sorted(CM.codes() - _OLD_INCHEON_CODES)  # 67개, 신설 코드만(post-reorg)


def test_era_relaxation_still_fails_when_almost_everything_is_missing():
    """제물포·영종(신설 인천 코드) 두 개만 있고 나머지 65개 시군구가 통째로 없다 —
    인천 두 코드만 봐서는 '어느 era 인지' 확정할 근거가 되지만, 인천 밖 시군구가
    빠진 것까지 완화가 눈감아 주면 안 된다."""
    rows = [_row("28125"), _row("28155")]
    expected = collect._effective_expected_codes(rows, CM)
    with pytest.raises(checks.CheckFailed):
        checks.check_regions(rows, collect._ExpectedCodes(expected))


def test_era_relaxation_does_not_excuse_missing_non_incheon_region():
    """인천 era 는 깨끗(신설 코드만, 일관됨)한데 강남구(11680) 하나가 빠졌다 —
    era 완화가 인천 그룹에만 적용돼야지, 다른 지역 결측까지 덮어 주면 안 된다."""
    rows = [_row(code) for code in _REALISTIC_CODES if code != "11680"]
    expected = collect._effective_expected_codes(rows, CM)
    with pytest.raises(checks.CheckFailed) as e:
        checks.check_regions(rows, collect._ExpectedCodes(expected))
    assert "11680" in str(e.value)


# ---------------------------------------------------------------------------
# R40 — 이름 겹침 검사. est(KOSIS)·eis 두 출처의 직종·산업 이름이 정규화를
# 거치고도 하나도 안 겹치면, 분류 체계 자체가 갈렸다는 신호다 — 카드가 조용히
# 비는 대신 수집을 시끄럽게 멈춘다.
# ---------------------------------------------------------------------------

def test_check_name_overlap_passes_when_names_overlap():
    checks.check_name_overlap({"경영·행정·사무직", "제조업"}, {"경영·행정·사무직", "금융업"})


def test_check_name_overlap_fails_when_nothing_overlaps():
    with pytest.raises(checks.CheckFailed):
        checks.check_name_overlap({"경영·행정·사무직"}, {"완전히 다른 이름"})


# --- R46: at_most — 우리가 받는 부분집합과 전국 총계 사이의 유일하게 참인 관계 ---

def test_check_against_total_at_most_passes_when_under():
    rows = [{"vacancy": 10}, {"vacancy": 20}]
    total = {"vacancy": 1000}          # 전국 총계 (지역무관·시도 잔여 포함)
    checks.check_against_total(rows, total, field="vacancy", mode="at_most")


def test_check_against_total_at_most_passes_when_equal():
    rows = [{"vacancy": 10}, {"vacancy": 20}]
    total = {"vacancy": 30}
    checks.check_against_total(rows, total, field="vacancy", mode="at_most")


def test_check_against_total_at_most_fails_when_over():
    """이중계상·자릿수 파싱 깨짐을 잡는 방향."""
    rows = [{"vacancy": 10}, {"vacancy": 20}]
    total = {"vacancy": 29}
    with pytest.raises(checks.CheckFailed):
        checks.check_against_total(rows, total, field="vacancy", mode="at_most")


# --- 리뷰 Important 4: 중첩 헤더 전개가 무너지는 모양(빈 축 값)을 직접 막는다 ---

def test_check_axis_values_passes_when_axes_are_filled():
    rows = [{"sigungu": "11110", "occupation": "경영·행정·사무직"}]
    checks.check_axis_values(rows, ["sigungu", "occupation"])


def test_check_axis_values_fails_on_a_collapsed_cell():
    """전개가 무너지면 남은 칸이 '' 로 남는다 — 그게 관찰 가능한 형태다."""
    rows = [{"sigungu": "11110", "occupation": ""}]
    with pytest.raises(checks.CheckFailed):
        checks.check_axis_values(rows, ["sigungu", "occupation"])


def test_check_axis_values_ignores_fields_that_are_not_this_grids_axes():
    """vacancy 행의 industry 는 애초에 그 그리드의 축이 아니라 늘 '' 이다 — 오탐 금지."""
    rows = [{"sigungu": "11110", "occupation": "관리직", "industry": ""}]
    checks.check_axis_values(rows, ["sigungu", "occupation"])


def test_check_sido_coverage_fails_when_a_metro_sido_is_missing():
    rows = [{"sido": "11"}, {"sido": "41"}]
    with pytest.raises(checks.CheckFailed):
        checks.check_sido_coverage(rows, ("11", "41", "28"))


def test_check_sido_coverage_passes_when_all_present():
    rows = [{"sido": "11"}, {"sido": "41"}, {"sido": "28"}, {"sido": "00"}]
    checks.check_sido_coverage(rows, ("11", "41", "28"))
