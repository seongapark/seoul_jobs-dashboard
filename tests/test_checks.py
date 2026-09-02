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
