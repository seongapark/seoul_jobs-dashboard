"""Task 7 Step 0 탐침 — (근무지역)시군구 × 직종_중분류를 얻는 유일한 길.

배경은 pipeline/eis.py 모듈 docstring 에 적었다: 유효구인구직현황(전체)
(menuId 020010020) 의 기본 레이아웃은 행=(지역별)시도, 열=마감년월이라 화면이
원하는 (근무지역)시군구 × 직종 분해를 안 준다. 다른 리포트(050010060)의 지역
필터는 시도 수준까지만 가고(tools/probe_flat_sigungu.py 참고 대상과는 다른
탐침 — 이건 별도로 남기지 않음), URL 파라미터로 레이아웃/지역을 지정하는 길도
없었다. 남는 건 좌측 "분석 항목" 트리에서 필드를 행/열 영역으로 끌어놓는 UI
조작뿐이다.

이 스크립트는 그 조작을 재현한다:
  1. 행/열 영역을 초기화한다 (#rowAdHocList1_5990_clear, #colAdHocList1_5990_clear)
  2. (근무지역)시군구, 직종_중분류를 순서대로 행 영역(#rowAdHocList1_5990)에 끌어놓는다
     (드래그당 필드 하나씩 — 나중에 놓은 필드가 계층의 바깥쪽이 된다)
  3. 돋보기(검색) 아이콘을 클릭해 재조회한다
  4. 로딩 스피너("작업 취소" 버튼)가 사라질 때까지 기다린다
  5. pipeline.olap._EXTRACT_JS 로 1페이지 분량을 읽어 확인한다

**깨지기 쉬움**: 이 좌측 필드초이서는 DevExtreme PivotGrid 가 아니라 EIS 가
자체 제작한 jQuery-UI 기반 "WISE" 위젯(class `wise-area-field`, id 접미사
`_5990`)이다. 요소 id/속성이 바뀌면(예: `_5990` 인스턴스 번호, `uni_nm` 속성명)
이 스크립트는 즉시 깨진다. 정기 수집 파이프라인에 그대로 쓰기 전에 재확인이
필요하다.

**중요 발견**: 이렇게 만든 (근무지역)시군구 × 직종_중분류 그리드는 페이지네이션
(`.dx-datagrid-pager`)으로 나뉜다 — 무한 스크롤이 아니다. 이 스크립트는 1페이지
(약 50행)만 읽는다. pipeline.olap.fetch_grid 는 Task 7 에서 이 상황(페이지 2개
이상)을 감지하면 OlapPaginationError 를 내도록 고쳤다 — 스크롤 누적으로 조용히
잘린 그리드를 반환하지 않는다. 페이지네이션 자체를 넘겨가며 누적하는 로직은
아직 없다 (후속 과제).

정중함: page.goto 1회.
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

from pipeline import eis_report
from pipeline import olap as olap_mod

OUT_DIR = Path(__file__).resolve().parents[1] / "tests/fixtures"


def main() -> None:
    url = eis_report.viewer_url(eis_report.REPORTS["유효구인구직"])
    print("viewer url:", url)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=90_000)
        page.wait_for_selector("div.dx-pivotgrid-area-data", timeout=60_000)
        page.wait_for_timeout(500)

        page.click("#rowAdHocList1_5990_clear")
        page.wait_for_timeout(300)
        page.click("#colAdHocList1_5990_clear")
        page.wait_for_timeout(300)

        row_area = page.locator("#rowAdHocList1_5990")
        for field in ["(근무지역)시군구", "직종_중분류"]:
            src = page.locator(f'li[uni_nm="{field}"][prev-container="allList"]')
            src.scroll_into_view_if_needed()
            src.drag_to(row_area)
            page.wait_for_timeout(500)

        # 돋보기(검색) 아이콘 — 좌표 클릭. 아이콘 자체는 크기 0 래퍼라 locator
        # 클릭이 "not visible" 로 실패해 좌표를 직접 쓴다 (툴바 우상단 고정 위치).
        page.mouse.click(1178, 31)

        for _ in range(60):
            if page.locator("text=작업 취소").count() == 0:
                break
            page.wait_for_timeout(1000)
        page.wait_for_timeout(500)

        grid = page.evaluate(olap_mod._EXTRACT_JS)
        header, *body = grid
        print("header:", header)
        print("row count (page 1 only, no pagination follow-up):", len(body))
        for row in body[:10]:
            print("  ", row)

        pager = page.locator(".dx-datagrid-pager .dx-page")
        print("페이지 수:", pager.count())

        browser.close()


if __name__ == "__main__":
    main()
