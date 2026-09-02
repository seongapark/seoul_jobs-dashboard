"""Task 9b Step 4 — 유효구인구직 기본 레이아웃(마감년월 축) 실측 탐침.

확인할 것: (a) 기간 축 컬럼의 실제 이름, (b) 받아지는 개월 수, (c) 시도
이름 표기. 정중함 원칙: 뷰어를 한 번만 연다(fetch_and_parse_grid 내부에서
page.goto 1회).
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

from pipeline import eis_report, olap

_PERIOD_KEYS = ("마감년월", "기간", "년월")
_SIDO_KEYS = ("(지역별)시도", "지역")


def main() -> None:
    url = eis_report.viewer_url(eis_report.REPORTS["유효구인구직"])
    print("== viewer url:", url)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        parsed = olap.fetch_and_parse_grid(url, browser=browser)
        browser.close()

    rows = parsed.rows
    print("== 행 수:", len(rows))
    if not rows:
        print("!! 행이 비었다")
        return

    print("== 컬럼 이름:", sorted(rows[0].keys()))

    period_key = next((k for k in _PERIOD_KEYS if k in rows[0]), None)
    print("== 기간 축 컬럼 이름:", period_key)
    if period_key:
        periods = sorted({r.get(period_key) for r in rows})
        print("== 관측된 기간 값:", periods)
        print("== 개월 수:", len(periods))

    sido_key = next((k for k in _SIDO_KEYS if k in rows[0]), None)
    print("== 시도 축 컬럼 이름:", sido_key)
    if sido_key:
        print("== 시도 이름 표기:", sorted({r.get(sido_key) for r in rows}))

    print("== 요약행(summaries) 수:", len(parsed.summaries))
    if parsed.summaries:
        print("== 요약행 샘플:", parsed.summaries[0])


if __name__ == "__main__":
    main()
