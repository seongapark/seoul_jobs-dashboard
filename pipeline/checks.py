"""수집 결과가 배포돼도 되는지 본다.

이 파일의 목적은 하나다 — 조용히 틀린 값이 화면에 오르는 것을 막는다.
어긋나면 예외를 던지고, 호출부는 커밋하지 않는다.
"""
from __future__ import annotations

import re

INCHEON_OLD_TO_NEW = {
    "28110": ["28125", "28155"],   # 중구 → 제물포·영종
    "28140": ["28125"],            # 동구 → 제물포
    "28260": ["28275", "28290"],   # 서구 → 서해·검단
}

SEAM_RATIO = 2.0  # 표 경계에서 이보다 크게 튀면 코드 매핑 의심


class CheckFailed(RuntimeError):
    pass


def check_regions(rows, cm) -> None:
    seen = {row["sigungu"] for row in rows}
    missing = cm.codes() - seen
    if missing:
        raise CheckFailed(f"시군구 {len(missing)}개가 비었다: {sorted(missing)[:5]} …")


def check_not_all_zero(rows, field) -> None:
    if not any(row.get(field) for row in rows):
        raise CheckFailed(f"{field} 가 전부 0 이다 — 수집이 비었다")


def check_not_identical_to_previous(rows, previous) -> None:
    if previous and rows == previous:
        raise CheckFailed("전월과 완전히 동일하다 — 새 자료가 아니다")


def check_incheon_codes(rows) -> None:
    by_period: dict[str, set[str]] = {}
    for row in rows:
        by_period.setdefault(row["period"], set()).add(row["sigungu"])
    for period, codes in by_period.items():
        for old, news in INCHEON_OLD_TO_NEW.items():
            overlap = [n for n in news if n in codes]
            if old in codes and overlap:
                raise CheckFailed(
                    f"{period}: 개편 전 {old} 와 신설 {overlap} 가 함께 있다 — 더하면 이중계상")


def check_est_seam(rows) -> None:
    by_key: dict[tuple, dict[str, int]] = {}
    for row in rows:
        by_key.setdefault((row["occupation"], row["item"]), {})[row["period"]] = row["value"]
    for key, series in by_key.items():
        if "202502" in series and "202601" in series:
            before, after = series["202502"], series["202601"]
            if before and (after / before > SEAM_RATIO or before / max(after, 1) > SEAM_RATIO):
                raise CheckFailed(f"표 경계에서 값이 튄다 {key}: {before} → {after}")


# ---------------------------------------------------------------------------
# R13 — 총계 행을 실제 검산으로 쓴다.
#
# 데이터 계약: "유효구직건수의 분해값을 더해 총계로 쓰지 않는다 — 총계는 총계
# 행에서 받는다." 이 함수가 그 규칙을 실제로 강제한다. mode 에 따라 방향이
# 반대다 — 이게 이 파일에서 가장 헷갈리기 쉬운 규칙이라 여기 다시 적는다:
#
#   - "equality" (유효구인인원용): 구인 1건은 근무지역을 정확히 하나 낸다.
#     그래서 시군구 합은 총계와 정확히 같아야 한다. 다르면(모자라든 남든)
#     행이 소실됐거나 이중계상됐다는 뜻 — 두 경우 다 실패다.
#   - "at_least" (유효구직건수용): 구직 1건은 희망근무지역을 여럿 낼 수
#     있다(1인 다건/다지역). 그래서 시군구 합이 총계를 넘는 것은 정상이고
#     기대되는 동작이다. 실패 조건은 반대 방향뿐이다 — 합이 총계에 못
#     미치면, 그건 정상적인 초과의 부재가 아니라 행이 빠졌다는 뜻이다.
# ---------------------------------------------------------------------------

def check_against_total(rows, total, *, field, mode) -> None:
    parts = sum(row.get(field, 0) for row in rows)
    expected = total.get(field, 0)
    if mode == "equality":
        if parts != expected:
            raise CheckFailed(
                f"{field}: 시군구 합({parts}) 이 총계({expected}) 와 다르다 — "
                f"행이 소실됐거나 이중계상됐다")
    elif mode == "at_least":
        if parts < expected:
            raise CheckFailed(
                f"{field}: 시군구 합({parts}) 이 총계({expected}) 보다 작다 — 행이 빠졌다")
    else:
        raise ValueError(f"알 수 없는 mode: {mode!r}")


# ---------------------------------------------------------------------------
# Task 9b (R19/R27) — 마감년월 축 시계열 전용 검사.
#
# 시계열은 선으로 잇는 용도이지 더하는 용도가 아니다(R19). 그리드가 기간
# 축에 끼워 넣는 요약 행(예: "합계")이 그대로 섞이면 화면이 그것을 한 달인
# 양 선으로 이어 버린다 — check_series_shape 의 period 6자리 검사가 그것을
# 기계로 막는 자리다.
# ---------------------------------------------------------------------------

_PERIOD_RE = re.compile(r"^\d{6}$")


def check_series_shape(rows) -> None:
    """(sido, period) 조합이 유일하고, period 가 전부 YYYYMM 6자리인지 본다."""
    seen: set[tuple] = set()
    for row in rows:
        period = row.get("period")
        if not (isinstance(period, str) and _PERIOD_RE.match(period)):
            raise CheckFailed(
                f"period 가 YYYYMM 6자리 숫자가 아니다: {period!r} — "
                f"그리드가 끼워 넣은 요약 행(예: '합계')일 수 있다")
        key = (row.get("sido"), period)
        if key in seen:
            raise CheckFailed(f"(sido, period) 조합이 중복이다: {key}")
        seen.add(key)


def check_series_months(rows, minimum: int = 2) -> None:
    """어느 시도든 관측 월이 minimum 개 미만이면 실패한다."""
    by_sido: dict[str, set[str]] = {}
    for row in rows:
        by_sido.setdefault(row["sido"], set()).add(row["period"])
    for sido, periods in by_sido.items():
        if len(periods) < minimum:
            raise CheckFailed(
                f"{sido}: 관측 월이 {len(periods)}개뿐이다 (최소 {minimum}개 필요)")
