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


# ---------------------------------------------------------------------------
# R50 (2026-09-02) — `check_incheon_codes` 는 **실데이터가 반증해서 지웠다.**
#
# 그 검사는 "같은 달에 개편 전 코드와 신설 코드가 함께 값을 가지면 더할 때
# 이중계상이다"라고 봤다. 전제(R17)는 "어느 달이든 EIS 는 한 시대의 코드만
# 준다"였는데, 실측이 그 전제를 깼다 — 2026년 07월 (근무지역) 축 그리드는 옛
# 코드와 신설 코드를 **함께** 준다:
#
#     28110 중구 (0/1,428) · 28140 동구 (0/405) · 28260 서구 (159/6,282)   [옛]
#     28125 제물포 (939/243) · 28155 영종 (549/535)
#     28275 서해 (1,823/1,524) · 28290 검단 (831/736)                      [신설]
#
# 그리고 이중계상이 아니다. 인천 시군구를 **전부** 더하고 시도 잔여를 얹으면
# 시도 값과 정확히 맞는다 (9,268 / 86,627). 신설 코드만 쓰면 구인 159·구직
# 7,968 이 그냥 사라진다. 즉 두 시대는 **상호배타**이고, 옛 코드에 남은 구직건은
# 중복이 아니라 아직 이관되지 않은 건이다.
#
# 그래서 이 검사는 옳은 수집을 막는 검사였다. 지운 자리는 비워 두지 않았다 —
# `check_sido_totals`(R54, 아래)가 그 자리를 대신한다. 그쪽이 더 강하다:
# 옛·신 코드가 겹쳐 정말로 이중계상되면 시도 합이 시도 값을 넘어 바로 걸린다.
# **다시 넣지 마라** — 넣으려면 위 실측을 먼저 반박해야 한다.
#
# `INCHEON_OLD_TO_NEW` 자체는 남는다. collect._effective_expected_codes 가
# "옛 코드가 다 사라진 미래의 달"에 완전성 기준을 완화하는 데 여전히 쓴다.
# ---------------------------------------------------------------------------


def check_est_seam(rows) -> None:
    # C2 — est 행의 분류 축은 표에 따라 갈린다: 직종별 표(est.collect)는
    # `occupation` 을, 산업별 표(est.collect_industry)는 `industry` 를 싣고
    # 서로 상대의 키를 아예 갖지 않는다. `row["occupation"]` 직접 인덱싱은
    # 산업 행에서 KeyError 로 죽어, 값이 튀는지 판정하기도 전에 수집이 다른
    # 이유로 무너진다. 한 번의 호출이 받는 rows 는 늘 한 표에서 오므로
    # (run_halfyear 가 collector 하나를 부른다) 두 축이 한 키로 뭉칠 일은 없다.
    by_key: dict[tuple, dict[str, int]] = {}
    for row in rows:
        axis = row.get("occupation") or row.get("industry")
        by_key.setdefault((axis, row["item"]), {})[row["period"]] = row["value"]
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


# ---------------------------------------------------------------------------
# R54 — 시도 검산: 약한 그물(전국 총계 at_most)에 강한 그물을 더한다.
#
# 실측(2026-09-02, 2026년 07월, (근무지역) 축)이 **등호**가 성립함을 보였다:
#
#     시군구 합  +  시도 잔여  ==  시도 값
#     서울   15,125 + 0        == 15,125   (구직 107,164 + 248,729 == 355,893)
#     인천    9,268 + 0        ==  9,268   (구직  38,774 +  47,853 ==  86,627)
#     경기   48,938 + 0        == 48,938   (구직 273,931 +  43,823 == 317,754)
#            ^ 경기는 일반구를 모시로 합산 이관(R53)한 뒤의 값이다. 이관 전에는
#              구인 26,649 로 45.5% 가 비어 이 등호가 성립하지 않았다.
#
# 이건 R46 의 전국 총계 at_most 보다 훨씬 강하다 — 시도마다, 측정값마다 정확히
# 맞아야 하므로 한 시도에서만 행이 새거나 겹쳐도 잡힌다. **R46 은 그대로 둔다**
# (이중 그물이다).
#
# 잔여가 무엇인지는 fetchers._split_metro 독스트링에 적었다 — 요약하면 "시도까지만
# 적힌 건"(시군구 축에 '서울특별시' 같은 이름으로 나타난다)과 우리 70개 표에 없는
# 시군구 행이다. 검산이 실패하면 그 정의부터 의심하라.
# ---------------------------------------------------------------------------

def check_sido_totals(rows, residuals, sido_rows, *, field) -> None:
    """시도별로 (시군구 합 + 잔여) 가 시도 값과 같은지 본다."""
    parts: dict[str, int] = {}
    for row in rows:
        sigungu = row.get("sigungu")
        if not sigungu:
            continue
        parts[sigungu[:2]] = parts.get(sigungu[:2], 0) + row.get(field, 0)

    by_sido = {row.get("sido"): row for row in sido_rows}
    for sido, total_row in sorted(by_sido.items()):
        if sido in (None, "00"):          # 전국 총계는 R46 이 따로 본다
            continue
        expected = total_row.get(field)
        if expected is None:
            continue                      # 이 시도 파일에 없는 측정값이면 건너뛴다
        got = parts.get(sido, 0) + (residuals or {}).get(sido, {}).get(field, 0)
        if got != expected:
            raise CheckFailed(
                f"{field}: 시도 {sido} 의 시군구 합+잔여({got}) 가 시도 값({expected}) 과 "
                f"다르다 (시군구 합 {parts.get(sido, 0)}, 잔여 "
                f"{(residuals or {}).get(sido, {}).get(field, 0)})")
