"""EIS OLAP (지역별)시도 x 마감년월 그리드 한 조각을 시계열 행으로 편다.

Task 9b (R19/R27) — 플랜에 없던 태스크였다. §4.1 카드 2(24개월 추세),
§4.2 카드 8·§4.3 카드 11(이번 달 대 최근 6개월 평균)이 이력을 요구하는데
`pipeline/eis.py` 의 `collect_*_sido` 는 최신 한 달치만 편다.

R27 은 애초 "축을 드래그로 옮기지 않고 기본 레이아웃을 그대로 받으면
24개월이 한 번에 온다"고 전제했는데, **R34 실측으로 이 전제가 틀린 것으로
확인됐다** — EIS 큐브는 마감년월을 행 축에 놓아도 뷰어 URL 의 closYm 이
가리키는 한 달치만 돌려준다(경위는 `pipeline/collect.py` 의 `run_series`
독스트링과 `task-9b-report.md` 의 "R34 실측" 절 참고). 그래서 R39 가
방식을 바꿨다: closYm 을 달마다 바꿔가며 한 조각씩 받아 쌓는다. 이 모듈
(`series.py`)은 그 한 조각(한 리포트 응답)을 시계열 행으로 펴는 순수
변환만 하고, 여러 조각을 병합해 이력을 보존하는 일은 `collect.run_series`
가 한다.

이 모듈은 `pipeline/eis.py` 의 `collect_*` 함수들과 같은 모양의 순수
변환 함수만 둔다 — 네트워크를 모른다. 지역 이름 매핑·숫자 파싱은
`pipeline.eis` 의 공개 헬퍼(`period_code`/`to_number`/`sido_code`)와
사설 헬퍼(`_first`/`_SEEKERS_KEYS` — 유효구직 컬럼명이 리포트마다
"유효구직건수(전체)"/"유효구직자수(전체)" 로 갈리는 문제를 이미 해결해
뒀다)를 그대로 재사용한다. 지역 이름이 매핑에 없으면 `eis.UnknownRegion`
을 그대로 올린다 — 조용히 버리지 않는다.

R4 와 마찬가지로 이 파일이 내는 행에는 sigungu/center 가 없고 sido 만
있다 — 시군구 축과 절대 섞지 않는다(이 프로젝트에서 가장 위험한 실패는
"에러 없이 축만 틀리게" 나가는 것이다).

R19 — 유효는 월별 합산 금지: 이 모듈은 시군구를 더하지도, 여러 달을
더하지도 않는다. 시계열은 선으로 잇는 용도다.
"""
from __future__ import annotations

from pipeline import eis

# 기간 축 컬럼 이름을 "마감년월" 하나로 고정하지 않는다 — 리포트마다 표기가
# 다를 수 있다(브리프 지시). 이 순서로 찾는다.
_PERIOD_KEYS = ("마감년월", "기간", "년월")

# 24개월 상한 — 시도별로 최근 이만큼만 남기고 오래된 것은 버린다.
SERIES_MONTHS = 24


class MissingPeriodColumn(ValueError):
    """기간 축 컬럼을 하나도 못 찾았을 때 낸다.

    `KeyError` 를 그대로 올리면 무엇을 찾다가 실패했는지 안 보인다 — 시도한
    컬럼 이름을 메시지에 남긴다.
    """


def _period_text(row: dict) -> str:
    for key in _PERIOD_KEYS:
        if key in row:
            return row[key]
    raise MissingPeriodColumn(
        f"기간 축 컬럼을 못 찾는다 (시도한 이름: {_PERIOD_KEYS}) — "
        f"실제 컬럼: {sorted(row.keys())}")


def _cap_recent_months(rows: list[dict]) -> list[dict]:
    """시도별로 최근 SERIES_MONTHS 개월만 남기고 나머지는 버린다."""
    by_sido: dict[str, list[dict]] = {}
    for row in rows:
        by_sido.setdefault(row["sido"], []).append(row)

    out: list[dict] = []
    for group in by_sido.values():
        group.sort(key=lambda r: r["period"], reverse=True)
        out.extend(group[:SERIES_MONTHS])
    return out


def collect_vacancy_series(rows: list[dict]) -> list[dict]:
    """(지역별)시도 x 마감년월 기본 레이아웃 유효구인구직 그리드를 시계열로 편다."""
    out = []
    for row in rows:
        out.append({
            "period": eis.period_code(_period_text(row)),
            "sido": eis.sido_code(row.get("(지역별)시도") or row.get("지역")),
            "vacancy": eis.to_number(row.get("유효구인인원(전체)")),
            "seekers": eis.to_number(eis._first(row, eis._SEEKERS_KEYS)),
        })
    return _cap_recent_months(out)


def collect_insured_series(rows: list[dict]) -> list[dict]:
    """(사업장)시도 x 마감년월 기본 레이아웃 피보험자 그리드를 시계열로 편다."""
    out = []
    for row in rows:
        out.append({
            "period": eis.period_code(_period_text(row)),
            "sido": eis.sido_code(row.get("(사업장)시도") or row.get("지역")),
            "insured": eis.to_number(row.get("피보험자수(전체)")),
        })
    return _cap_recent_months(out)
