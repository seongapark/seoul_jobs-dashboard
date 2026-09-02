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
# 행에서 받는다." 이 함수가 그 규칙을 실제로 강제한다.
#
# R46 (Task 15a 실측, 2026-09-02) — 실제로 쓰는 mode 는 이제 "at_most" 하나다.
# 나머지 둘은 실데이터와 맞지 않는 것으로 **실측으로 반증됐다**:
#
#   - EIS 그리드의 총계 행은 **전국** 총계이고, 그 안에는 `지역무관` 과
#     시도 잔여 멤버(희망근무지를 시도까지만 적은 구직자)까지 들어 있다
#     (실측: 전체 고유 라벨 합계 165,821 = 총계 165,821). 우리는 수도권
#     시군구만 받으므로 "equality" 는 **구조적으로 영원히 실패한다.**
#   - "at_least" 의 근거("1인 다건이라 시군구 합이 총계를 넘는다")도 방향이
#     반대였다. 실측: 서울 시군구 합 107,164 < 시도 총계 355,893 이고, 그
#     차이 248,729 는 `서울특별시` 잔여 멤버 한 행이었다. 즉 초과가 아니라
#     **부족**이 정상이다.
#
# 그래서 "at_most"(분해합 ≤ 총계)로 간다 — 이것이 우리가 받는 부분집합과
# 총계 행 사이의 **유일하게 참인 관계**다. 검사를 무른 것이 아니다:
#
#   - 합이 총계를 넘는 실패(페이지 중복으로 행이 이중계상되거나 자릿수 파싱이
#     깨지는 것 — 바로 R47 이 잡은 그런 종류)는 여전히 여기서 잡힌다.
#   - 반대 방향(행 누락으로 합이 줄어드는 것)은 시군구 70개 완전성 검사
#     (check_regions)가 이미 잡는다. **두 검사가 양방향을 함께 덮는다.**
#
# "equality"/"at_least" 는 옛 계약을 명시적으로 남겨 두려고 그대로 둔다
# (tests/test_checks.py 가 셋 다 검증한다) — 다만 실제 배선
# (collect.MEASURE_MODES)은 at_most 만 쓴다.
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
    elif mode == "at_most":
        if parts > expected:
            raise CheckFailed(
                f"{field}: 수도권 분해합({parts}) 이 전국 총계({expected}) 를 넘는다 — "
                f"행이 이중계상됐거나 숫자 파싱이 깨졌다")
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


# ---------------------------------------------------------------------------
# R40 — 두 출처(est/eis)의 직종·산업 이름이 정규화(eis.normalize_name)를 거치고도
# 하나도 안 겹치면, 분류 체계 자체가 갈렸다는 신호다. 카드가 조용히 비는 대신
# 여기서 시끄럽게 실패한다 — 이 저장소의 원칙 그대로("조용히 틀리느니 시끄럽게
# 실패한다").
# ---------------------------------------------------------------------------

def check_name_overlap(names_a, names_b) -> None:
    """두 이름 집합의 교집합이 비면 실패한다."""
    if not (set(names_a) & set(names_b)):
        raise CheckFailed(
            f"이름이 하나도 안 겹친다 — 분류 체계가 달라졌을 수 있다: "
            f"{sorted(names_a)[:3]} vs {sorted(names_b)[:3]}")


# ---------------------------------------------------------------------------
# 리뷰 Important 4 (2026-09-02) — 중첩 세로 헤더 전개가 무너지는 모양을 직접 막는다.
#
# olap._EXTRACT_JS 는 중첩 축의 rowspan/colspan 을 펴서 레벨마다 칸을 채우는데,
# <tr> 이 레벨 수보다 적은 td 를 내면 루프가 멈추고 **남은 칸이 '' 로 남는다.**
# 그 뒤 fetchers._metro_only 가 '' 을 비수도권 이름으로 보고 버리므로, 지역 축이
# 무너지면 행이 통째로 사라지고(=시군구 70개 완전성 검사가 잡는다) 지역이 아닌
# 축(직종·산업)이 무너지면 '' 인 채로 살아남는다 — 그 두 번째 경우를 잡는 검사다.
# ---------------------------------------------------------------------------

def check_axis_values(rows, fields) -> None:
    """축 필드가 빈 값인 행이 있으면 실패한다."""
    for row in rows:
        blank = [field for field in fields if not str(row.get(field) or "").strip()]
        if blank:
            raise CheckFailed(
                f"축 값이 비어 있다 {blank}: {row} — 중첩 헤더 전개가 무너졌을 수 있다")


def check_sido_coverage(rows, expected) -> None:
    """수도권 시도가 전부 관측됐는지 본다.

    mobility 는 시군구 완전성 검사도 총계 검산도 받지 않는 유일한 데이터셋이라
    그물이 check_not_all_zero 하나뿐이었는데, 그건 한 행만 살아남아도 통과한다 —
    반쪽짜리 mobility.json 이 조용히 나갈 수 있었다.
    """
    seen = {row.get("sido") for row in rows}
    missing = sorted(set(expected) - seen)
    if missing:
        raise CheckFailed(f"시도 {missing} 가 비었다 — 수집이 반쪽이다")
