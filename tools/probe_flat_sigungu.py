"""Task 7 Step 0 탐침 — 큰 그리드가 스크롤인지 페이지네이션인지 실측한다.

Task 6 은 유효구인구직현황(전체)의 기본 레이아웃(17행, (지역별)시도 단일 축)
만으로 "dataScroll=Y 무한 스크롤이 있다"고 가정하고 그 가정 위에서
pipeline.olap.fetch_grid 를 스크롤-누적 루프로 짰다. 17행은 애초에 스크롤이
필요 없는 크기라 그 가정 자체는 검증된 적이 없었다 — Task 6 보고서도 이 점을
후속 과제로 남겼다.

이 스크립트는 행 축을 (지역별)시군구 **단독**(중첩 없는 평평한 단일 필드,
전국 약 250개)으로 바꿔 진짜로 스크롤이 걸리는지 본다. 결과: 걸리지 않는다.
대신 DevExtreme 데이터그리드 스타일 페이저(`.dx-datagrid-pager`, 페이지당
50행, 총 6페이지)로 나뉜다. `.dx-pivotgrid-area-data .dx-scrollable-container`
는 DOM 에 존재하지만(스크롤 자체는 가능) 그 안의 행 수 자체가 50개뿐이라
스크롤해도 새 행이 늘지 않는다 — pipeline.olap.fetch_grid 의 예전 로직은 이걸
"안정화됐다"고 착각해 50행짜리 그리드를 예외 없이 반환했을 것이다.

이 발견으로 pipeline/olap.py 에 OlapPaginationError 를 추가했다(Task 7) —
페이지가 2개 이상이면 스크롤을 시도하기도 전에 시끄럽게 실패한다.

정중함: page.goto 1회.
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

from pipeline import eis_report
from pipeline import olap as olap_mod


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
        src = page.locator('li[uni_nm="(지역별)시군구"][prev-container="allList"]')
        src.scroll_into_view_if_needed()
        src.drag_to(row_area)
        page.wait_for_timeout(500)

        page.mouse.click(1178, 31)  # 돋보기(검색) 아이콘, 좌표 클릭 (probe_field_relocation.py 참고)

        for _ in range(60):
            if page.locator("text=작업 취소").count() == 0:
                break
            page.wait_for_timeout(1000)
        page.wait_for_timeout(500)

        pager = page.locator(".dx-datagrid-pager .dx-page")
        scroller = page.locator("div.dx-pivotgrid-area-data .dx-scrollable-container")
        print("페이저 존재:", pager.count(), "| 스크롤 컨테이너 존재:", scroller.count())

        grid = page.evaluate(olap_mod._EXTRACT_JS)
        header, *body = grid
        print("header:", header)
        print("row count (page 1 only):", len(body))
        print("first 3:", body[:3])
        print("last 3:", body[-3:])

        browser.close()


if __name__ == "__main__":
    main()
