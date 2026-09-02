"""워크플로 진입점.

`.github/workflows/collect-*.yml` 이 `main()` 하나를 모드 셋(`monthly`·
`series`·`halfyear`) 중 하나로 부른다(`python -m pipeline.cli <모드>`).
이 파일은 **무엇을 언제 부를지만 안다** — 어떻게 받는지(레이아웃 드래그,
그리드 파싱, 검산)는 전부 `pipeline.collect`/`pipeline.fetchers` 몫이다.

전역 제약: 검사가 실패하면 0 이 아닌 코드로 죽어 워크플로의 커밋 단계가
실행되지 않는다 — 그래서 `collect.run_*` 가 올리는 예외(`checks.CheckFailed`
등)를 여기서 잡아 삼키지 않는다. 잡는 예외는 "무엇이 없는지 사람이 읽을
메시지로 죽이고 싶은" 두 자리(모르는 모드, KOSIS_API_KEY 없음)뿐이다.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright

from pipeline import center_map, collect, fetchers, series

ROOT = Path(__file__).resolve().parent.parent


def latest_month() -> str:
    """오늘 기준 2개월 전 YYYYMM.

    EIS OLAP 리포트는 두 달 지연돼 확정된다 — 9월에 돌리면 7월치를 받는다
    (task-15a 실측: probe 시점 2026-09 에 2026-07 이 최신 확정월이었다).
    연도 산술은 0-based 월 인덱스로 해서 1·2월의 연말 경계(전년도로 넘어가는
    것)를 조건문 없이 자연스럽게 처리한다.
    """
    today = date.today()
    total = today.year * 12 + (today.month - 1) - 2
    year, month0 = divmod(total, 12)
    return f"{year:04d}{month0 + 1:02d}"


def _halfyear_period() -> str:
    """상반기(`YYYY01`)·하반기(`YYYY02`).

    직종별사업체노동력조사는 1월·7월을 기준으로 반기마다 조사되고 그 결과가
    약 5개월 뒤 KOSIS 에 공표된다(`pipeline/est.py` TABLES: 2026-09 시점에
    "202601" 이 이미 열려 있다 — task-9c/15a 실측). 수집 워크플로가 6월
    20일·12월 20일에 도는 것도 그 공표 시점에 맞춘 것이다. 그래서 상반월
    (1~6월)에 실행되면 그 해 상반기를, 하반월(7~12월)에 실행되면 그 해
    하반기를 요청한다. 아직 공표 전에 워크플로가 (수동으로) 일찍 돌면
    KOSIS 가 값을 못 주고 `checks.check_not_all_zero` 가 시끄럽게 실패한다
    — 조용히 빈 자료가 나가는 것보다 그게 낫다.
    """
    today = date.today()
    half = "01" if today.month <= 6 else "02"
    return f"{today.year:04d}{half}"


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _previous_monthly(out_dir: Path) -> dict:
    """`run_monthly` 의 `previous` 인자 — 이름 -> 지난달 rows(raw list).

    `run_monthly` 의 `check_not_identical_to_previous` 는 `previous` 를 rows
    리스트와 곧바로 비교한다(`{"rows": [...]}` 로 감싸지 않는다 — collect.py
    주석 참고). 그래서 파일에서 읽은 뒤 `rows` 만 뽑아 건넨다. 파일이 없으면
    (첫 수집) 그 이름은 아예 넣지 않는다 — `(previous or {}).get(name)` 이
    `None` 이 되어 검사가 자연히 건너뛰어진다.
    """
    out: dict[str, list] = {}
    for name in fetchers.MONTHLY_SPECS:
        data = _load_json(out_dir / f"{name}.json")
        if data is not None:
            out[name] = data.get("rows", [])
    return out


def _series_full_months(latest: str) -> list[str]:
    """`latest` 를 포함해 과거로 `series.SERIES_MONTHS` 개월, 오래된 순으로."""
    year, month = int(latest[:4]), int(latest[4:])
    months = []
    for _ in range(series.SERIES_MONTHS):
        months.append(f"{year:04d}{month:02d}")
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(months))


def _series_periods_needed(out_dir: Path, latest: str) -> list[str]:
    """받을 달 목록 — 시계열은 백필이다.

    첫 수집은 `series.SERIES_MONTHS`(24)개월을 다 받아야 하고, 이후 수집은
    새 달만 더한다. 그 판단은 부르는 쪽(cli) 몫이다(`fetchers._fetch_series`
    독스트링) — 기존 `data/*_series.json` 을 읽어 이미 있는 달을 뺀다.
    데이터셋(`vacancy_series`/`insured_series`)마다 이미 받은 달이 다를 수
    있어(한쪽만 지난 수집에서 실패했을 수 있다) 데이터셋별 부족분의
    합집합을 받는다 — 한쪽이 처진 채로 조용히 넘어가지 않는다.
    """
    full = set(_series_full_months(latest))
    needed: set[str] = set()
    for name in fetchers.SERIES_SPECS:
        data = _load_json(out_dir / f"{name}.json")
        existing = {row["period"] for row in (data or {}).get("rows", [])}
        needed |= full - existing
    return sorted(needed)


def _previous_series(out_dir: Path) -> dict:
    """`run_series` 의 `previous` 인자 — 이름 -> 지난 파일 그대로(`{"rows": [...]}`).

    `run_series` 는 내부에서 스스로 `.get(name, {}).get("rows", [])` 로
    rows 를 뽑는다(`run_monthly` 의 previous 계약과 다르다 — collect.py
    `run_series` 독스트링 참고) — 그래서 여기서는 파일을 풀어 헤치지 않고
    읽은 그대로 건넨다.
    """
    out: dict[str, dict] = {}
    for name in fetchers.SERIES_SPECS:
        data = _load_json(out_dir / f"{name}.json")
        if data is not None:
            out[name] = data
    return out


def _compare_names(out_dir: Path) -> set[str] | None:
    """`run_halfyear(compare_names=...)` 에 넘길 vacancy.json 의 직종 이름 집합.

    9c 가 만든 `checks.check_name_overlap` 을 실전 경로에 건다(9c 리뷰
    지적 — 만들고도 부르는 곳이 없어 안전망이 실전에 안 걸려 있었다).
    `vacancy.json` 이 아직 없으면(첫 수집) `None` 으로 건너뛰되, 조용히
    지나가면 안전망이 있으나 마나이므로 건너뛴다는 사실을 로그로 남긴다.
    """
    data = _load_json(out_dir / "vacancy.json")
    if data is None:
        print("halfyear: vacancy.json 이 아직 없다 — 직종 이름 겹침 검사를 건너뛴다 "
              "(첫 수집이라 비교할 상대가 없다).")
        return None
    return {row["occupation"] for row in data.get("rows", []) if row.get("occupation")}


def main(mode: str) -> int:
    out_dir = ROOT / "data"

    if mode == "monthly":
        cm = center_map.load(out_dir / "center_map.json")
        period = latest_month()
        previous = _previous_monthly(out_dir)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                result = collect.run_monthly(
                    period, out_dir=out_dir,
                    fetchers=fetchers.monthly_fetchers(browser=browser, cm=cm),
                    cm=cm, previous=previous)
            finally:
                browser.close()
        print(f"monthly({period}): {result}")
        return 0

    if mode == "series":
        latest = latest_month()
        periods = _series_periods_needed(out_dir, latest)
        if not periods:
            # fetchers._fetch_series 는 periods=[] 도 SeriesBackfillError 다 —
            # "이미 다 쌓여 있어 받을 달이 없다"는 정상 상태를 여기서 판단하고
            # 빈 목록으로 부르지 않는다.
            print(f"series: {latest} 까지 이미 다 쌓여 있다 — 받을 달이 없어 건너뛴다.")
            return 0
        previous = _previous_series(out_dir)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                result = collect.run_series(
                    out_dir=out_dir,
                    fetchers=fetchers.series_fetchers(periods, browser=browser),
                    previous=previous)
            finally:
                browser.close()
        print(f"series({periods[0]}..{periods[-1]}, {len(periods)}개월): {result}")
        return 0

    if mode == "halfyear":
        try:
            api_key = os.environ["KOSIS_API_KEY"]
        except KeyError:
            raise SystemExit(
                "KOSIS_API_KEY 환경변수가 없다 — GitHub Secret 또는 로컬 export 로 넣어라.")
        period = _halfyear_period()
        result = collect.run_halfyear(
            period, out_dir=out_dir, api_key=api_key,
            compare_names=_compare_names(out_dir))
        print(f"halfyear({period}): {result}")
        return 0

    raise SystemExit(f"모르는 모드: {mode!r} (monthly|halfyear|series 중 하나)")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else ""))
