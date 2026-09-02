"""수집을 엮는다.

원칙: 검사를 다 통과한 뒤에야 파일을 쓴다. 절반만 갱신된 상태가 가장 나쁘다.

R4 — 시도 파일은 따로.
  시도 총계(예: vacancy_sido.json)는 시군구 값을 더해 만들지 않는다. 유효구직
  건수는 1인이 여러 희망근무지역을 낼 수 있어(1인 다건) 시군구 합이 시도
  총계보다 커질 수 있다 — 그 관계를 검산하는 건 checks.check_against_total
  의 몫이지, run_monthly 가 시군구를 더해 시도 값을 "만드는" 게 아니다.
  대신 fetchers 에 "<name>_sido" 키로 별도 수집기(예: eis.collect_vacancy_sido)
  를 넣으면 그 결과를 그대로 "<name>_sido.json" 에 쓴다. 시도 행은 sigungu
  가 아니라 sido 필드를 쓰므로(pipeline/eis.py 참고) 70개 시군구 완전성 검사·
  인천 개편 코드 검사 대상에서 뺀다 — 애초에 시군구가 아니다.

시군구 완전성 검사는 raw cm.codes() 70개를 그대로 쓰지 않는다 — 이유는
_effective_expected_codes 의 docstring 참고(요약: center_map.json 이 인천
개편 전후 코드를 영구히 함께 보존해서, raw 70개짜리 완전성은 실데이터로
"영원히" 만족 불가능하다).

R18 (Fix round 1 컨트롤러 지시) — checks.check_against_total 을 실제 경로에서
호출한다. R13 은 "총계 행을 진짜 검산으로 쓴다"는 규칙을 만들었지만, 애초
구현은 run_monthly 가 그 함수를 호출하지 않아 죽은 코드였다 — 그리드 총계
행이 시군구 합과 어긋나도 아무도 못 잡았다. 그래서 fetcher 계약을 넓힌다:
각 fetcher 는 rows 뿐 아니라 그 rows 의 총계(totals)를 함께 돌려준다
(`Fetched(rows, totals)`). totals 는 {필드명: 총계값} 매핑이거나, 그리드가
총계를 못 줬으면 명시적으로 None 이다 — 조용히 검사를 건너뛰지 않는다.
총계가 있어야 하는 데이터셋(시군구 검사 대상인 vacancy/placement/insured)
이 None 으로 오면 그 자체가 실패다(그리드 모양이 바뀌어 총계 파싱이
조용히 깨졌다는 신호일 수 있다 — "총계가 없으니 통과"는 절대 선택지가
아니다).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from pipeline import checks

# Task 15a — 산업 축 데이터셋(vacancy_industry/insured_industry)은 같은 리포트를
# 산업_대분류 축으로 한 번 더 받은 것이라 **행 모양과 측정값 필드가 짝 데이터셋과
# 똑같다**(eis.collect_vacancy/collect_insured 를 그대로 쓴다). 이름 매핑이 없으면
# FIELD_OF.get(base, base) 가 "vacancy_industry" 라는 있지도 않은 필드로
# check_not_all_zero 를 돌려 매달 오탐으로 죽는다 — 그래서 여기 명시한다.
FIELD_OF = {"vacancy": "vacancy", "placement": "placements",
            "insured": "insured", "mobility": "movers",
            "vacancy_industry": "vacancy", "insured_industry": "insured"}

# R18 — 데이터셋별로 검산할 (필드, mode) 목록.
#
# R46 (Task 15a 실측, 2026-09-02) — 전부 "at_most" 다. 애초 설계는 구인/취업/
# 피보험을 equality, 유효구직을 at_least 로 놓았는데 **둘 다 실데이터로
# 반증됐다**: 그리드 총계 행은 전국 총계이고 `지역무관`·시도 잔여 멤버까지
# 포함하는데 우리는 수도권만 받으므로 equality 는 구조적으로 영원히 실패하고,
# at_least 의 방향(시군구 합 > 총계)도 실측과 반대였다(서울 시군구 합 107,164
# < 시도 총계 355,893, 차이는 `서울특별시` 잔여 멤버 한 행). 근거 전문은
# checks.check_against_total 위 주석 참고.
#
# 검사를 무른 것이 아니다 — "수도권 분해합 ≤ 전국 총계" 는 우리가 받는 것과
# 총계 행 사이의 유일하게 참인 관계이고, 합이 부풀어 오르는 실패(페이지 중복
# 이중계상·자릿수 파싱 깨짐 — R47 이 잡은 바로 그런 것)를 여전히 잡는다.
# 반대 방향(누락)은 시군구 70개 완전성 검사가 잡으므로 두 검사가 양방향을
# 함께 덮는다. totals=None 이 실패라는 것도 그대로다(아래 run_monthly).
MEASURE_MODES: dict[str, tuple[tuple[str, str], ...]] = {
    "vacancy": (("vacancy", "at_most"), ("seekers", "at_most")),
    "placement": (("placements", "at_most"),),
    "insured": (("insured", "at_most"),),
    # Task 15a — 산업 축은 같은 측정값을 다른 분해축으로 받은 것이라 검산 규칙이
    # 짝 데이터셋과 같다. 축이 달라도 총계는 하나이므로 여기서 갈라질 이유가 없다.
    "vacancy_industry": (("vacancy", "at_most"), ("seekers", "at_most")),
    "insured_industry": (("insured", "at_most"),),
}

_SIDO_SUFFIX = "_sido"
# Task 15a — 산업 축 데이터셋도 시군구 축이다(행마다 sigungu 가 있다). 시군구
# 완전성·인천 개편 코드 검사를 똑같이 받아야 맞다 — 빼면 산업 축 파일만
# 시군구가 빠진 채로 조용히 나갈 수 있다.
_SIGUNGU_CHECKED = ("vacancy", "placement", "insured",
                    "vacancy_industry", "insured_industry")

# 리뷰 Important 4 — mobility 는 시군구 완전성 검사에도 MEASURE_MODES 에도 없어
# 그물이 check_not_all_zero 하나뿐이었다(한 행만 살아남아도 통과한다). 시도 축
# 데이터셋이므로 수도권 시도 3개가 다 있는지로 완전성을 본다.
METRO_SIDO_CODES = ("11", "41", "28")
_SIDO_CHECKED: dict[str, tuple[str, ...]] = {"mobility": METRO_SIDO_CODES}


class Fetched(NamedTuple):
    """fetcher 하나의 결과 — 행과, 그 행들의 합이 맞아야 하는 총계(R18).

    totals 는 그리드가 별도로 준 총계 행에서 온 {필드: 값} 매핑이다. 총계를
    못 받았으면 조용히 검사를 건너뛰지 않고 반드시 None 이라고 명시한다 —
    시군구 완전성 검사 대상(vacancy/placement/insured, _sido 접미사 제외)
    데이터셋이 totals=None 으로 오면 run_monthly 가 그 자체를 실패로 본다.
    """

    rows: list[dict]
    totals: dict | None


def _base_name(name: str) -> str:
    return name[: -len(_SIDO_SUFFIX)] if name.endswith(_SIDO_SUFFIX) else name


class _ExpectedCodes:
    """checks.check_regions 가 요구하는 `.codes()` 인터페이스만 제공하는 얇은 어댑터."""

    def __init__(self, codes: set[str]):
        self._codes = codes

    def codes(self) -> set[str]:
        return self._codes


def _effective_expected_codes(rows, cm):
    """cm.codes() 를 그대로 완전성 기준으로 쓰면 인천 개편 전후 코드가 매달
    함께 다 있어야 하는데, 그건 check_incheon_codes 가 금지하는 바로 그
    상황이다 — center_map.json 은 옛 코드(28110/28140/28260)를 과거 자료
    색인용으로 영구 보존하므로 70개 안에 개편 전·후가 함께 들어 있다. 즉
    raw cm.codes() 완전성은 실데이터로 "영원히" 만족될 수 없다(개편 이후엔
    옛 코드가 다시 나올 리 없으므로). 그래서 실제로 관측된 쪽 era 만
    요구하도록 완화한다 — 두 era 가 함께 관측되는 진짜 이상 상황은 여전히
    바로 다음 줄의 check_incheon_codes 가 잡는다. 이 조정이 없으면 매달
    수집이 영구히 실패한다.
    """
    seen = {row["sigungu"] for row in rows if "sigungu" in row}
    expected = set(cm.codes())
    for old, news in checks.INCHEON_OLD_TO_NEW.items():
        if old in seen and not any(new in seen for new in news):
            expected -= set(news)          # 아직 개편 전이다 — 신설 코드는 요구하지 않는다
        elif old not in seen and any(new in seen for new in news):
            expected.discard(old)          # 이미 개편됐다 — 옛 코드는 더는 요구하지 않는다
    return expected


def run_monthly(period, *, out_dir, fetchers, cm, previous=None):
    collected: dict[str, Fetched] = {name: fetch(period) for name, fetch in fetchers.items()}

    for name, fetched in collected.items():
        rows = fetched.rows
        base = _base_name(name)
        field = FIELD_OF.get(base, base)
        if not name.endswith(_SIDO_SUFFIX) and base in _SIGUNGU_CHECKED:
            expected = _effective_expected_codes(rows, cm)
            checks.check_regions(rows, _ExpectedCodes(expected))
            checks.check_incheon_codes(rows)
            # R18 — 총계 검산. 그리드가 총계를 못 줬으면(totals=None) 조용히
            # 넘어가지 않고 그 자체를 실패로 본다.
            if fetched.totals is None:
                raise checks.CheckFailed(
                    f"{name}: 그리드 총계가 없다 — 검산 없이 통과시킬 수 없다")
            for total_field, mode in MEASURE_MODES.get(base, ()):
                checks.check_against_total(rows, fetched.totals, field=total_field, mode=mode)
        expected_sido = _SIDO_CHECKED.get(name)
        if expected_sido:
            checks.check_sido_coverage(rows, expected_sido)
        checks.check_not_all_zero(rows, field)
        # previous 는 지난달에 파일로 쓴 rows 그대로(raw list)다 — Fetched 로
        # 감싸지 않는다. run_monthly 가 쓰는 파일 자체가 {"rows": [...]} 모양
        # 이므로 "지난달 산출물"을 자연스럽게 그대로 넘길 수 있게 한다.
        checks.check_not_identical_to_previous(rows, (previous or {}).get(name))

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for name, fetched in collected.items():
        (out_dir / f"{name}.json").write_text(
            json.dumps({"period": period, "collected_at": stamp, "rows": fetched.rows},
                       ensure_ascii=False),
            encoding="utf-8")
    return {name: len(fetched.rows) for name, fetched in collected.items()}


def _series_key(row: dict) -> tuple:
    """시계열 행의 병합 키. 지금은 (sido, period) 뿐이지만, 직종 축 등이
    늘어나면 여기만 넓히면 되도록 함수로 뽑아 둔다."""
    return (row.get("sido"), row.get("period"))


def run_series(*, out_dir, fetchers, previous=None):
    """마감년월 축 시계열(Task 9b, R19/R27/R39)을 모아 쓴다.

    R34 실측(task-9b-report.md 참고)으로 확인된 것 — EIS 유효구인구직/
    피보험자 OLAP 큐브는 마감년월을 행 축에 놓아도 뷰어 URL 의 closYm 이
    가리키는 딱 그 한 달치만 돌려준다. "축만 옮기면 한 그리드로 24개월이
    한 번에 온다"는 애초 전제(R27)는 이 실측으로 깨졌다. 그래서 R39 가
    방식을 바꿨다: closYm 을 달마다 바꿔가며 **한 번에 한 조각씩** 받아
    쌓는다(첫 수집은 closYm 을 24번 바꿔 24개월을 채우고, 이후 수집은
    새 달 하나만 더한다) — 그 반복 자체(몇 번을 어떤 closYm 으로 부를지)
    는 이 함수의 몫이 아니라 나중 태스크(pipeline/fetchers.py)가 맡는다.
    run_series 는 "한 번에 받은 조각을 기존 이력에 안전하게 얹는 것"만
    안다 — 원래 있던 이력을 새 조각으로 덮어써서 날리면(R19 가 막으려던
    바로 그 실패) 안 되므로, 새로 받은 행을 previous 에 병합한다.

    previous 는 run_monthly 의 previous 와 같은 결이다 — 지난번에 쓴
    파일 내용 그대로(`{"rows": [...]}` 모양)를 데이터셋 이름으로 담은
    매핑이고, 없으면(첫 수집) 새로 받은 행만으로 시작한다.

    병합 규칙(`_series_key`, (sido, period)): 같은 키가 겹치면 **새로
    받은 값이 이긴다** — 가결산이 확정치로 정정돼 내려올 수 있어서다.
    병합한 뒤에 `series.SERIES_MONTHS`(24) 상한을 적용한다 — 새로 받은
    조각에만 걸면 옛 이력이 잘리므로, 반드시 **병합된 전체**에 걸어야
    한다. 검사(`check_series_shape`/`check_series_months`)도 병합
    결과에 대해 돌고, 검사를 다 통과한 뒤에야 파일을 쓴다(run_monthly 와
    같은 원칙 — 절반만 갱신된 상태를 만들지 않는다).

    fetcher 계약은 `run_monthly` 와 다르다: 시계열은 총계 검산이 필요
    없으므로(월별 합산 자체가 R19 위반이다) `Fetched` 로 감싸지 않고
    `() -> list[dict]` 를 그대로 받는다 — period 인자도 없다(그 순간의
    closYm 이 어떤 값인지는 fetcher 가 알아서 정하고, run_series 는 결과
    행이 어느 달인지만 병합 키로 본다).
    """
    from pipeline import series

    collected: dict[str, list[dict]] = {name: fetch() for name, fetch in fetchers.items()}

    merged: dict[str, list[dict]] = {}
    for name, rows in collected.items():
        prior_rows = (previous or {}).get(name, {}).get("rows", [])
        by_key: dict[tuple, dict] = {_series_key(row): row for row in prior_rows}
        for row in rows:
            by_key[_series_key(row)] = row  # 겹치면 새 값이 이긴다 — 확정치 정정 대응
        merged[name] = series._cap_recent_months(list(by_key.values()))

    for rows in merged.values():
        checks.check_series_shape(rows)
        checks.check_series_months(rows)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for name, rows in merged.items():
        (out_dir / f"{name}.json").write_text(
            json.dumps({"rows": rows, "collected_at": stamp}, ensure_ascii=False),
            encoding="utf-8")
    return {name: len(rows) for name, rows in merged.items()}


def _row_names(rows) -> set[str]:
    """행에 실린 occupation_name/industry_name(있는 쪽)을 모은다 — None 은 뺀다.

    est.collect() 는 occupation_name 을, collect_industry() 는 industry_name 을
    싣는다(R33/R40) — run_halfyear 는 어느 collector 가 왔는지 모르므로 둘 다 본다.
    """
    names: set[str] = set()
    for row in rows:
        for key in ("occupation_name", "industry_name"):
            name = row.get(key)
            if name is not None:
                names.add(name)
    return names


def run_halfyear(period, *, out_dir, api_key, collector=None, compare_names=None):
    from pipeline import est

    collector = collector or est.collect
    rows = collector([period], api_key=api_key)
    checks.check_est_seam(rows)
    checks.check_not_all_zero(rows, "value")

    # R40 — 비교 대상 이름 집합이 주어졌을 때만 겹침을 검사한다. 안 주면
    # 조용히 건너뛴다(R18 의 "배선 없는 죽은 검사" 재발 방지: 여기서
    # 명시적으로 건너뛴다는 것을 보여 둔다).
    if compare_names is not None:
        checks.check_name_overlap(_row_names(rows), compare_names)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "est.json").write_text(
        json.dumps({"period": period, "rows": rows}, ensure_ascii=False),
        encoding="utf-8")
    return {"est": len(rows)}
