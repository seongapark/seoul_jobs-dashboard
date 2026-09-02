"""주소·레이아웃·파서를 데이터셋마다 잇는다 — 수집이 실제로 도는 자리.

`collect.run_monthly`/`run_series` 는 `fetchers` 를 인자로 받아 부르기만 하고,
그 fetchers 를 만드는 곳이 지금까지 없었다. 이 모듈이 그 자리다. 하는 일은
데이터셋마다 늘 같은 네 단계다 — 아래 골격(`_fetch_monthly`)에 한 번만 쓰고,
데이터셋별로 다른 것(리포트·행 축·파서·측정값 컬럼)만 `MONTHLY_SPECS` 표에 둔다:

  1. `month_url` 로 뷰어 주소를 얻고 `closYm` 을 그 달로 갈아끼운다
  2. `layout.set_layout` 으로 화면이 요구하는 축을 만든다 (좌측 필드초이서 드래그)
  3. `olap.fetch_and_parse_grid` 로 그리드를 읽는다 (페이지네이션·요약행 분리 포함)
  4. 그리드 모양을 `eis`/`series` 순수 변환기가 기대하는 행 모양으로 맞춰 넘긴다

4단계(`_normalize`)가 필요한 이유는 실측으로 확인됐다(2026-09-02, 아래 "실측"
절). `parse_grid` 가 내는 dict 와 `eis.collect_*` 가 기대하는 dict 는 같지 않다.

--------------------------------------------------------------------------
실측 (2026-09-02, 유효구인구직 menuId=020010020 뷰어, tools/probe_fetchers.py)
--------------------------------------------------------------------------

1) **측정값 컬럼에 마감년월 접두가 붙는다.** 마감년월이 열 축에 있으면 헤더는
   `"2026년 07월_유효구인인원(전체)"` 이고 `"마감년월"` 이라는 컬럼은 없다.
   `eis.collect_vacancy` 는 반대로 `row["마감년월"]` 과 `row["유효구인인원(전체)"]`
   를 기대한다. `_normalize` 가 접두를 떼어 `마감년월` 컬럼으로 옮긴다.
   덤으로 **요청한 closYm 과 그리드가 돌려준 달이 같은지 대조한다** — closYm 이
   안 먹었는데 조용히 넘어가면 24개월 백필이 같은 달로 다 채워진다.

2) **그리드는 전국이고, 시군구 축에는 시군구가 아닌 멤버가 섞여 있다.**
   (근무지역)시군구 단독 그리드는 고유 라벨 289개였고 그 안에 `지역무관`,
   시도 잔여 멤버(`서울특별시` — 희망근무지를 시도까지만 적은 구직자),
   전국 시군구가 다 들어 있었다. `eis._code()` 는 이 중 무엇도 모른다
   (`UnknownRegion`). 그래서 `_metro_only` 가 **수도권 70개 시군구 이름과
   정확히 일치하는 행만** 남긴다. 이건 "모르는 지역을 조용히 버린다"가 아니라
   전국 큐브에서 수도권 대시보드용 부분집합을 고르는 일이고, 너무 많이
   버렸으면 `checks.check_regions`(70개 완전성)가 바로 잡는다.

3) **그리드의 총계 행은 전국 총계다.** 실측: 총계 유효구인인원 165,821 =
   전국 모든 멤버(지역무관·시도 잔여 포함)의 합. 수도권만 남긴 행의 합과는
   당연히 다르다. 이 모듈은 브리프대로 요약 행에서 총계를 만들어 넘기되,
   그 값이 `collect.MEASURE_MODES` 의 검산과 맞지 않는다는 사실을 보고서에
   적어 두었다(컨트롤러 판정 필요) — **여기서 몰래 검사를 무르지 않는다.**

4) 중첩 축의 행 머리는 레벨마다 td 가 따로 있고 바깥 레벨은 rowspan 으로 그룹
   첫 행에만 그려진다. 이건 `olap._EXTRACT_JS` 에서 폈다(같은 커밋).

--------------------------------------------------------------------------
왜 모듈 수준 `MONTHLY`/`SERIES` dict 가 아니라 만들어 주는 함수인가
--------------------------------------------------------------------------
전역 제약이 "모든 수집기는 fetch/browser/page 를 주입받는다" 이다. 브라우저를
모듈 수준 dict 에 담으면 그 제약이 깨지고 테스트가 네트워크에 나간다. 그래서
데이터셋 표(`MONTHLY_SPECS`/`SERIES_SPECS`)는 모듈 수준 데이터로 두고,
`monthly_fetchers(...)`/`series_fetchers(...)` 가 `run_monthly`/`run_series` 가
요구하는 모양(`{이름: (period) -> Fetched}` / `{이름: () -> list[dict]}`)을
그때그때 만들어 준다.
"""
from __future__ import annotations

import re
import time
from typing import Callable, NamedTuple

import requests

from pipeline import checks, eis, eis_report, layout, olap, series
from pipeline.collect import Fetched

# 달 사이에 두는 간격 (정중함). 24개월 백필이 24회 요청이라 몰아치지 않는다.
SERIES_PAUSE_SECONDS = 2.0

# 요약(총계) 행을 알아보는 라벨 — olap._SUMMARY_ROW_LABELS 와 같은 근거다.
TOTAL_LABELS = frozenset({"총계"})

# 그룹 소계 행의 라벨 접미 (실측: "2025직종_관리직(임원·부서장) 전체").
# 소계 행은 본문에 섞이면 이중계상이 되므로 뺀다.
_SUBTOTAL_SUFFIX = " 전체"

_PERIOD_RE = re.compile(r"^\d{6}$")
_PERIOD_PREFIX_RE = re.compile(r"^(\d{4}년\s*\d{2}월)_(.+)$")
_CLOS_YM_RE = re.compile(r"([?&])closYm=[^&]*")


class FetchError(RuntimeError):
    """수집한 그리드가 요청과 다르거나 기대한 컬럼이 없을 때 낸다."""


class SeriesBackfillError(RuntimeError):
    """시계열 백필에서 절반을 넘는 달이 실패했을 때 낸다 — 반쪽 수집을 조용히 넘기지 않는다."""


# ---------------------------------------------------------------------------
# 데이터셋 표 — 여기만 데이터셋마다 다르다.
# ---------------------------------------------------------------------------

class Spec(NamedTuple):
    """데이터셋 하나를 어떻게 받을지.

    rows      : 행 축 (**바깥→안쪽**, layout.set_layout 과 같은 규약)
    region    : 수도권 필터와 코드 변환을 걸 컬럼 이름
    sido_axis : region 이 시도 축이면 True (시군구 이름표가 아니라 시도 이름표로 거른다)
    parse     : eis/series 의 순수 변환기
    needs_cm  : parse 가 center_map 을 받는가
    measures  : 총계 행에서 뽑을 {출력 필드: (그리드 컬럼 후보들)}
    """

    report: str
    rows: tuple[str, ...]
    region: str
    sido_axis: bool
    parse: Callable
    needs_cm: bool
    measures: dict


_VACANCY_MEASURES = {
    "vacancy": ("유효구인인원(전체)",),
    # 리포트마다 표기가 갈린다 — eis._SEEKERS_KEYS 와 같은 이유다.
    "seekers": eis._SEEKERS_KEYS,
}
_PLACEMENT_MEASURES = {"placements": ("취업건수(월)",)}
_INSURED_MEASURES = {
    "insured": ("피보험자수(전체)",),
    "gained": ("취득자수(월)",),
    "lost": ("상실자수(월)",),
}

# R48 (컨트롤러 판정, 2026-09-02) — **실측 범위를 여기 밝혀 둔다.**
# 아래 표에서 살아있는 화면으로 확인한 것은 `유효구인구직`(menuId 020010020)
# 리포트의 필드 이름뿐이다. `취업건수`·`피보험자`·`경력직이동` 세 리포트의
# 좌측 분석항목 `uni_nm` 값과 (사업장) 축 이름은 **실측하지 않았고**,
# `pipeline/eis.py` 가 읽는 컬럼 이름에서 유도했다. 셋을 다 실측하는 비용이
# 위험보다 크다는 판정이라 그대로 둔다 — 이름이 틀리면 `layout.LayoutError`
# ("필드를 못 찾는다")로 시끄럽게 드러나고, 그때 실측 한 번이면 고쳐진다.
# 조용히 틀린 축으로 수집될 길은 없다(layout 의 드래그·렌더 검증 참고).
MONTHLY_SPECS: dict[str, Spec] = {
    "vacancy": Spec("유효구인구직", ("(근무지역)시군구", "직종_중분류"),
                    "(근무지역)시군구", False, eis.collect_vacancy, True, _VACANCY_MEASURES),
    # 산업 축은 직종 축과 같은 리포트를 다른 레이아웃으로 한 번 더 받는다 —
    # 한 그리드에 직종과 산업을 함께 놓으면 셀 수가 폭증한다.
    "vacancy_industry": Spec("유효구인구직", ("(근무지역)시군구", "산업_대분류"),
                             "(근무지역)시군구", False, eis.collect_vacancy, True,
                             _VACANCY_MEASURES),
    # R45 — 시도 축은 (근무지역)이다. 스펙 §2.2 "화면은 (근무지역) 축으로
    # 통일한다"에 맞춘다(실측 차이: 2026-07 서울 15,125 vs (지역별) 29,196).
    "vacancy_sido": Spec("유효구인구직", ("(근무지역)시도",),
                         "(근무지역)시도", True, eis.collect_vacancy_sido, False,
                         _VACANCY_MEASURES),
    "placement": Spec("취업건수", ("(근무지역)시군구", "직종_중분류"),
                      "(근무지역)시군구", False, eis.collect_placement, True,
                      _PLACEMENT_MEASURES),
    "placement_sido": Spec("취업건수", ("(근무지역)시도",),
                           "(근무지역)시도", True, eis.collect_placement_sido, False,
                           _PLACEMENT_MEASURES),
    "insured": Spec("피보험자", ("(사업장)시군구", "직종_중분류"),
                    "(사업장)시군구", False, eis.collect_insured, True, _INSURED_MEASURES),
    "insured_industry": Spec("피보험자", ("(사업장)시군구", "산업_대분류"),
                             "(사업장)시군구", False, eis.collect_insured, True,
                             _INSURED_MEASURES),
    "insured_sido": Spec("피보험자", ("(사업장)시도",),
                         "(사업장)시도", True, eis.collect_insured_sido, False,
                         _INSURED_MEASURES),
    "mobility": Spec("경력직이동", ("(사업장)시도", "산업_대분류", "산업(이전)_대분류"),
                     "(사업장)시도", True, eis.collect_mobility, False,
                     {"movers": ("경력이동자수(월)",)}),
}

SERIES_SPECS: dict[str, Spec] = {
    "vacancy_series": Spec("유효구인구직", ("(근무지역)시도",),
                           "(근무지역)시도", True, series.collect_vacancy_series, False,
                           _VACANCY_MEASURES),
    "insured_series": Spec("피보험자", ("(사업장)시도",),
                           "(사업장)시도", True, series.collect_insured_series, False,
                           _INSURED_MEASURES),
}

# 마감년월은 늘 열 축에 둔다. 그래야 측정값 컬럼에 마감년월 접두가 붙고,
# `_normalize` 가 그것을 요청한 closYm 과 대조할 수 있다 (실측 1 참고).
PERIOD_COLUMN = "마감년월"

# 그리드 축 이름 -> 그 축이 만들어 내는 출력 행의 필드 (리뷰 Important 4).
# 중첩 헤더 전개가 무너지면 채워지지 않은 칸이 '' 로 남는데, 지역 축이 무너진
# 행은 _metro_only 가 통째로 버려서(=완전성 검사가 잡는다) 눈에 안 띄지만
# 직종·산업 축이 무너진 행은 '' 인 채로 살아남는다. 그 두 번째 경우를 잡으려면
# "이 데이터셋이 실제로 요청한 축"이 무엇인지 알아야 한다 — 이 표가 그것이다.
# (예: vacancy 행의 industry 는 애초에 이 그리드의 축이 아니라 늘 '' 이므로
# 검사 대상이 아니다. 축만 골라 봐야 오탐이 없다.)
_OUTPUT_FIELD_OF_AXIS = {
    "(근무지역)시군구": "sigungu",
    "(사업장)시군구": "sigungu",
    "(지역별)시군구": "sigungu",
    "(근무지역)시도": "sido",
    "(사업장)시도": "sido",
    "(지역별)시도": "sido",
    "직종_중분류": "occupation",
    "산업_대분류": "industry",
    "산업(이전)_대분류": "prev_industry",
}


def _axis_fields(spec: Spec) -> list[str]:
    return [_OUTPUT_FIELD_OF_AXIS[axis] for axis in spec.rows if axis in _OUTPUT_FIELD_OF_AXIS]


# ---------------------------------------------------------------------------
# 주소
# ---------------------------------------------------------------------------

def month_url(menu_id: str, period: str, *, get=requests.get) -> str:
    """뷰어 주소를 얻어 `closYm=YYYYMM` 을 적용한다 (있으면 갈아끼운다).

    문자열 치환으로 한다 — 주소의 다른 파라미터(`USER`, `assign_name`,
    `reportId`)는 이미 퍼센트 인코딩된 base64 라, 파싱해서 다시 조립하면
    인코딩이 미묘하게 달라질 수 있다. 건드리지 않는 게 안전하다.
    """
    if not _PERIOD_RE.match(period or ""):
        raise ValueError(f"period 는 YYYYMM 6자리여야 한다: {period!r}")
    url = eis_report.viewer_url(menu_id, get=get)
    if _CLOS_YM_RE.search(url):
        return _CLOS_YM_RE.sub(rf"\1closYm={period}", url, count=1)
    return f"{url}{'&' if '?' in url else '?'}closYm={period}"


def _period_label(period: str) -> str:
    return f"{period[:4]}년 {period[4:]}월"


# ---------------------------------------------------------------------------
# 그리드 모양 맞추기
# ---------------------------------------------------------------------------

def _normalize(rows: list[dict], period: str) -> list[dict]:
    """그리드 dict 를 `eis.collect_*` 가 기대하는 dict 로 맞춘다 (실측 1).

    측정값 컬럼의 `"2026년 07월_"` 접두를 떼어 `마감년월` 컬럼으로 옮기고,
    그 달이 요청한 closYm 과 같은지 대조한다.
    """
    out = []
    for row in rows:
        fixed: dict = {}
        seen_label = None
        for key, value in row.items():
            found = _PERIOD_PREFIX_RE.match(key)
            if found:
                seen_label = found.group(1)
                fixed[found.group(2)] = value
            else:
                fixed[key] = value
        if seen_label is not None:
            if eis.period_code(seen_label) != period:
                raise FetchError(
                    f"그리드가 돌려준 마감년월({seen_label})이 요청한 closYm({period})과 "
                    "다르다 — closYm 이 안 먹었을 수 있다. 조용히 다른 달을 쓰지 않는다.")
            fixed.setdefault(PERIOD_COLUMN, seen_label)
        elif PERIOD_COLUMN not in fixed:
            # 리뷰 Important 2 — 요청한 달을 지어내 도장찍지 않는다. 예전엔
            # 여기서 _period_label(period) 로 채웠는데, 그러면 위의 closYm
            # 교차검증이 "헤더에 접두가 붙어 있을 때만" 도는 조건부가 된다.
            # EIS 가 접두를 안 붙이는 순간 그리드가 무엇을 돌려주든 모든 행이
            # 요청한 달로 찍히고, 24개월 백필이 같은 달로 다 채워질 수 있다.
            # PERIOD_COLUMN 은 설계상 항상 열 축이므로(위 PERIOD_COLUMN 참고)
            # 접두도 리터럴 컬럼도 없으면 "이 그리드는 이 모듈이 생각하는 것이
            # 아니다"라는 뜻이다 — 시끄럽게 실패한다.
            raise FetchError(
                f"행에 마감년월이 없다 — 측정값 컬럼에 '{_period_label(period)}_' 접두도, "
                f"리터럴 {PERIOD_COLUMN!r} 컬럼도 없다. 요청한 달을 지어내 찍지 않는다. "
                f"실제 컬럼: {sorted(row)}")
        out.append(fixed)
    return out


def _is_subtotal(row: dict, spec: Spec) -> bool:
    """그룹 소계 행인가 (실측: 라벨이 '… 전체' 로 끝난다).

    본문에 섞이면 이중계상이 된다. 바깥 레벨 소계는 모든 라벨 칸이 소계
    텍스트라 `_metro_only` 의 지역 이름 대조에서 이미 걸리지만, 안쪽 레벨
    소계(예: 시도는 '서울'인데 산업 칸이 'C 제조업 전체')는 여기서만 걸린다.
    """
    return any((row.get(field) or "").endswith(_SUBTOTAL_SUFFIX) for field in spec.rows)


def _metro_only(rows: list[dict], spec: Spec) -> list[dict]:
    """수도권 이름표와 정확히 일치하는 행만 남긴다 (실측 2).

    전국 큐브에서 수도권 부분집합을 고르는 일이다. 너무 많이 버리면
    `checks.check_regions`(시군구 70개 완전성)가 잡는다.
    """
    known = eis._SIDO_NAME_TO_CODE if spec.sido_axis else eis.SIGUNGU_NAME_TO_CODE
    return [row for row in rows
            if (row.get(spec.region) or "").strip() in known and not _is_subtotal(row, spec)]


def _totals(summaries: list[dict], spec: Spec) -> dict | None:
    """요약(총계) 행에서 `{필드: 값}` 을 만든다. 총계 행이 없으면 None (지어내지 않는다).

    실측 3 — 이 총계는 **전국** 총계다. 수도권만 남긴 본문 합과 맞지 않는
    것이 정상이므로, 이 값을 그대로 검산에 쓰는 `collect.MEASURE_MODES` 는
    컨트롤러 판정이 필요하다(보고서 참고). 여기서 값을 손보지는 않는다.
    """
    for row in summaries:
        if (row.get(spec.rows[0]) or "").strip() not in TOTAL_LABELS:
            continue
        totals = {}
        for field, columns in spec.measures.items():
            value = eis._first(row, tuple(columns))
            if value is None:
                raise FetchError(
                    f"총계 행에 {columns} 중 어느 컬럼도 없다 — 그리드 헤더가 바뀌었을 수 있다. "
                    f"실제 컬럼: {sorted(row)}")
            totals[field] = eis.to_number(value)
        return totals
    return None


def _grid(spec: Spec, period: str, *, browser, get, fetch) -> olap.ParsedGrid:
    url = month_url(eis_report.REPORTS[spec.report], period, get=get)
    return fetch(url, browser=browser,
                 after_load=lambda page: layout.set_layout(
                     page, rows=list(spec.rows), cols=[PERIOD_COLUMN]))


# ---------------------------------------------------------------------------
# 월별 수집기 (run_monthly 계약: (period) -> Fetched)
# ---------------------------------------------------------------------------

def _fetch_monthly(spec: Spec, period: str, *, browser, cm, get, fetch) -> Fetched:
    grid = _grid(spec, period, browser=browser, get=get, fetch=fetch)
    body = _metro_only(_normalize(grid.rows, period), spec)
    rows = spec.parse(body, cm) if spec.needs_cm else spec.parse(body)
    checks.check_axis_values(rows, _axis_fields(spec))
    return Fetched(rows, _totals(_normalize(grid.summaries, period), spec))


def monthly_fetchers(*, browser, cm, get=requests.get,
                     fetch=olap.fetch_and_parse_grid) -> dict[str, Callable[[str], Fetched]]:
    """`collect.run_monthly(fetchers=...)` 가 요구하는 모양을 만든다."""
    def make(spec: Spec):
        return lambda period: _fetch_monthly(spec, period, browser=browser, cm=cm,
                                             get=get, fetch=fetch)

    return {name: make(spec) for name, spec in MONTHLY_SPECS.items()}


# ---------------------------------------------------------------------------
# 시계열 수집기 (run_series 계약: () -> list[dict])
# ---------------------------------------------------------------------------

def _fetch_series(spec: Spec, periods, *, browser, get, fetch, sleep, log) -> list[dict]:
    """closYm 을 달마다 바꿔가며 한 조각씩 받아 잇는다 (R39).

    한 달이 실패하면 그 달만 건너뛴다 — 24개월 백필이 한 달 때문에 통째로
    죽으면 안 된다. 다만 건너뛴 달은 반드시 로그로 남기고, 실패가 절반을
    넘으면 `SeriesBackfillError` 를 낸다(조용한 반쪽 수집 금지).

    **0행도 실패다 (리뷰 Critical 1).** 예외를 세는 것만으로는 부족하다:
    그리드가 깨끗이 받아지고 파싱까지 됐는데 `_metro_only` 가 하나도 못
    맞추면(시도 라벨이 '서울' → '서울특별시' 로 바뀌기만 해도 그렇다) 예외
    없이 달마다 0행이 나온다. 그 아래에는 그물이 없다 — `run_series` 에는
    `check_not_all_zero` 의 짝이 없고 `check_series_shape([])`/
    `check_series_months([])` 는 둘 다 무사통과라, 빈 시계열 파일이 새
    `collected_at` 과 함께 조용히 덮어써진다. 그래서 **필터 뒤 0행이 된 달을
    실패한 달로 세어** 절반 규칙이 작동하게 하고, 백필 전체가 0행이면 그
    자체로 예외를 올린다.
    """
    periods = list(periods)
    rows: list[dict] = []
    failed: list[str] = []
    for index, period in enumerate(periods):
        if index:
            sleep(SERIES_PAUSE_SECONDS)     # 정중함 — 몰아치지 않는다
        try:
            grid = _grid(spec, period, browser=browser, get=get, fetch=fetch)
            month = spec.parse(_metro_only(_normalize(grid.rows, period), spec))
            checks.check_axis_values(month, _axis_fields(spec))
        except Exception as error:          # noqa: BLE001 — 한 달 실패는 건너뛴다
            failed.append(period)
            log(f"{period} 수집 실패 — 건너뛴다: {error!r}")
            continue
        if not month:
            failed.append(period)
            log(f"{period} 수집 결과가 0행이다 — 실패로 센다 "
                f"(그리드는 받았지만 {spec.region!r} 축에서 수도권 이름을 하나도 "
                f"못 맞췄다: 라벨 표기가 바뀌었을 수 있다)")
            continue
        rows.extend(month)

    if failed and len(failed) * 2 > len(periods):
        raise SeriesBackfillError(
            f"{len(periods)}개월 중 {len(failed)}개월이 실패했다(절반 초과): {failed} — "
            "반쪽짜리 이력을 조용히 쓰지 않는다.")
    if not rows:
        raise SeriesBackfillError(
            f"{len(periods)}개월을 다 돌았는데 남은 행이 하나도 없다 — 빈 시계열을 "
            "새 collected_at 과 함께 덮어쓰지 않는다.")
    return rows


def series_fetchers(periods, *, browser, get=requests.get,
                    fetch=olap.fetch_and_parse_grid, sleep=time.sleep,
                    log=print) -> dict[str, Callable[[], list[dict]]]:
    """`collect.run_series(fetchers=...)` 가 요구하는 모양을 만든다.

    periods 는 **받을 달 목록**이다 — 이미 파일에 있는 달을 다시 받지 않도록
    무엇을 받을지는 부르는 쪽이 정한다(첫 수집 24개월, 이후 1개월).
    """
    def make(spec: Spec):
        return lambda: _fetch_series(spec, periods, browser=browser, get=get,
                                     fetch=fetch, sleep=sleep, log=log)

    return {name: make(spec) for name, spec in SERIES_SPECS.items()}
