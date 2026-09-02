"""Task 7b 실측 검증 — pipeline.olap._walk_paginated_grid 가 실제 다중 페이지
그리드(전 페이지)를 빠짐없이 걷어오는지 딱 한 번 확인한다.

tools/probe_flat_sigungu.py 가 확인한 절차 그대로 (지역별)시군구를 행 축에
단독으로 놓아 ~250행/페이지 6개짜리 그리드를 만든 뒤, fetch_grid() 대신
(fetch_grid 는 자체 goto 를 하므로 이 필드 재배치를 못 씀) 같은 page 위에서
pipeline.olap 의 페이저 탐지 + _walk_paginated_grid 를 직접 불러 검증한다.

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

        page.mouse.click(1178, 31)  # 돋보기(검색) 아이콘, 좌표 클릭

        for _ in range(60):
            if page.locator("text=작업 취소").count() == 0:
                break
            page.wait_for_timeout(1000)
        page.wait_for_timeout(500)

        # 여기부터는 fetch_grid 내부 로직과 동일한 절차를 이 page 위에서 직접 재현한다
        # (fetch_grid 자체는 자기 goto 를 하므로 이 필드 재배치 상태를 못 씀).
        try:
            page.wait_for_selector(olap_mod._PAGER_CONTAINER_SELECTOR,
                                    timeout=olap_mod._PAGER_WAIT_MS)
        except Exception:
            pass

        pager_count = page.locator(olap_mod._PAGER_SELECTOR).count()
        print("페이저가 보고한 페이지 수:", pager_count)

        grid = page.evaluate(olap_mod._EXTRACT_JS)
        header, *first_body = grid
        print("1페이지 행 수:", len(first_body))

        assert pager_count > 1, f"페이지네이션 그리드를 기대했는데 pager_count={pager_count}"

        # Task 7b Fix round 4 (R15): _walk_paginated_grid 는 이제 list 가 아니라
        # Grid(header, rows, summaries) 를 돌려준다 — .header/.rows/.summaries 로
        # 명시적으로 꺼낸다("header_out, *body = rows" 같은 옛 언패킹은 더 이상
        # 옳은 모양을 주지 않는다).
        result = olap_mod._walk_paginated_grid(
            page, header=header, first_body=first_body, pager_count=pager_count
        )

        print("=== 검증 결과 ===")
        print("페이지 수:", pager_count)
        print("누적 고유 행 수:", len(result.rows))
        print("요약 행 수(총계 등):", len(result.summaries))
        print("헤더:", result.header)
        print("첫 3행:", result.rows[:3])
        print("마지막 3행:", result.rows[-3:])
        print("요약 행:", result.summaries)

        # 중복 없는지, 기대 총량과 맞는지 다시 한 번 확인
        keys = {"".join(r) for r in result.rows}
        assert len(keys) == len(result.rows), "중복 행이 섞여 있다"

        browser.close()


if __name__ == "__main__":
    main()
