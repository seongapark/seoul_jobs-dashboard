"""Task 15a Step 4 실측 — 가장 위험한 데이터셋 하나를 끝까지 받아 본다.

`vacancy`((근무지역)시군구 × 직종_중분류) 한 달치가 실제로 끝까지 받아지는지
본다: 주소 해석 → 드래그 레이아웃 → 페이지네이션 누적 → 파싱 → 수도권 필터 →
총계. 화면용 파일은 쓰지 않는다 (검사와 파일 쓰기는 collect.run_monthly 의 몫).

정중함: 브라우저 하나, page.goto 1회. 그 뒤 페이지 걷기는 olap 이 한다.

**깨지기 쉬움**: pipeline/layout.py 독스트링 참고 — 좌측 WISE 필드초이서
(`wise-area-field`, id 접미사 `_5990`)와 재조회 좌표 클릭에 기대는 경로다.
"""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

from pipeline import center_map, fetchers
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(name: str = "vacancy", period: str = "202607") -> None:
    cm = center_map.load(ROOT / "data/center_map.json")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            built = fetchers.monthly_fetchers(browser=browser, cm=cm)
            fetched = built[name](period)
        finally:
            browser.close()

    rows = fetched.rows
    print(f"[{name}] 행 수:", len(rows))
    print("총계(그리드 요약 행):", fetched.totals)
    if rows and "sigungu" in rows[0]:
        print("고유 시군구 수:", len({r["sigungu"] for r in rows}))
        print("고유 직종/산업 수:",
              len({r.get("occupation") or r.get("industry") for r in rows}))
    if rows and "sido" in rows[0]:
        print("시도:", sorted({r["sido"] for r in rows}))
    for key in ("vacancy", "seekers", "placements", "insured", "movers"):
        if rows and key in rows[0]:
            print(f"  합계 {key}:", sum(r[key] for r in rows))
    print("  표본 행:", rows[0] if rows else None)


if __name__ == "__main__":
    main(*sys.argv[1:])
