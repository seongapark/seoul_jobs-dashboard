"""Task 9b R34 실측 탐침 — EIS 가 마감년월을 몇 개월치나 들고 있는가.

컨트롤러 판정(R34): `pipeline/series.py`/`checks.py`/`run_series` 는 이미
브리프가 준 입력 계약(행마다 "마감년월" 필드가 있는 그리드)을 정확히
구현했으므로 손대지 않는다. 이 탐침을 실제 수집 파이프라인에 배선하는
일(드래그 조작 자체를 프로덕션 코드로 옮기는 일)은 시군구x직종 축(R11)과
마찬가지로 Task 15(`pipeline/fetchers.py`)로 미뤄져 있다 — 이 스크립트는
배선이 아니라 순수 탐침이다.

미룰 수 없는 것 하나만 본다: EIS 가 마감년월 축에 몇 개월치 데이터를 들고
있는가. 24개월이 안 되면 추세 카드(§4.1 카드 2 등) 설계 자체가 흔들리므로
Task 15 까지 미루지 않고 지금 확인한다.

`tools/probe_field_relocation.py` 가 확립한 조작을 그대로 본뜬다:
  1. 행/열 영역 초기화 (#rowAdHocList1_5990_clear, #colAdHocList1_5990_clear)
  2. 좌측 WISE 필드초이서에서 필드를 행 영역(#rowAdHocList1_5990)으로 드래그
  3. 돋보기(검색) 아이콘 좌표 클릭 → 재조회
  4. 로딩 스피너("작업 취소") 사라질 때까지 대기
  5. pipeline.olap._EXTRACT_JS 로 읽기

한 세션(goto 1회) 안에서 두 가지를 순서대로 본다:
  (a) 마감년월만 행 축에 — 가장 단순하고 명확한 개월 수 측정.
  (b) (지역별)시도 를 마감년월 바깥에 추가 — 시도 x 마감년월 중첩(series.py
      가 기대하는 실제 레이아웃에 가장 가깝다).

**깨지기 쉬움**: probe_field_relocation.py 와 동일한 위험 — WISE 위젯
(class `wise-area-field`, id 접미사 `_5990`)의 id/uni_nm 속성이 바뀌면
이 스크립트는 즉시 깨진다.

정중함: page.goto 1회.
"""
from __future__ import annotations

from playwright.sync_api import sync_playwright

from pipeline import eis_report
from pipeline import olap as olap_mod


def _requery_and_wait(page) -> None:
    # 돋보기(검색) 아이콘 — 좌표 클릭. 아이콘 자체는 크기 0 래퍼라 locator
    # 클릭이 "not visible" 로 실패해 좌표를 직접 쓴다 (툴바 우상단 고정 위치).
    page.mouse.click(1178, 31)
    for _ in range(60):
        if page.locator("text=작업 취소").count() == 0:
            break
        page.wait_for_timeout(1000)
    page.wait_for_timeout(500)


def _drag_to_row(page, field: str) -> None:
    row_area = page.locator("#rowAdHocList1_5990")
    src = page.locator(f'li[uni_nm="{field}"][prev-container="allList"]')
    count = src.count()
    if count == 0:
        raise RuntimeError(f"필드 '{field}' 를 allList 에서 못 찾는다 (uni_nm 불일치 의심)")
    src.first.scroll_into_view_if_needed()
    src.first.drag_to(row_area)
    page.wait_for_timeout(500)


def _extract(page):
    grid = page.evaluate(olap_mod._EXTRACT_JS)
    header, *body = grid
    return header, body


def main() -> None:
    url = eis_report.viewer_url(eis_report.REPORTS["유효구인구직"])
    print("viewer url:", url)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=90_000)
        page.wait_for_selector("div.dx-pivotgrid-area-data", timeout=60_000)
        page.wait_for_timeout(500)

        all_uni_nm = page.eval_on_selector_all(
            'li[prev-container="allList"]', "els => els.map(e => e.getAttribute('uni_nm'))")
        print("== allList 필드 목록:", all_uni_nm)

        # --- (a) 마감년월만 행 축에 ---
        page.click("#rowAdHocList1_5990_clear")
        page.wait_for_timeout(300)
        page.click("#colAdHocList1_5990_clear")
        page.wait_for_timeout(300)
        _drag_to_row(page, "마감년월")
        _requery_and_wait(page)

        header_a, body_a = _extract(page)
        print("\n== (a) 마감년월만 행 축 ==")
        print("header:", header_a)
        print("row count:", len(body_a))
        periods_a = sorted({row[0] for row in body_a if row})
        print("서로 다른 마감년월 값 수:", len(periods_a))
        if periods_a:
            print("가장 오래된 값:", periods_a[0], " / 가장 최근 값:", periods_a[-1])
        pager_a = page.locator(".dx-datagrid-pager .dx-page")
        print("페이지 수:", pager_a.count())

        # --- (b) (지역별)시도 를 마감년월 바깥에 추가 (시도 x 마감년월 중첩) ---
        page.click("#rowAdHocList1_5990_clear")
        page.wait_for_timeout(300)
        _drag_to_row(page, "마감년월")        # 먼저 놓은 게 안쪽(리프)
        _drag_to_row(page, "(지역별)시도")    # 나중에 놓은 게 바깥쪽
        _requery_and_wait(page)

        header_b, body_b = _extract(page)
        print("\n== (b) (지역별)시도 x 마감년월 중첩 ==")
        print("header:", header_b)
        print("row count:", len(body_b))
        for row in body_b[:20]:
            print("  ", row)
        pager_b = page.locator(".dx-datagrid-pager .dx-page")
        print("페이지 수:", pager_b.count())

        browser.close()


if __name__ == "__main__":
    main()
