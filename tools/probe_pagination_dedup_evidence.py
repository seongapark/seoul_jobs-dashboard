"""Task 7b 후속 확인 — 262 vs 267 불일치의 원인을 리터럴 행 텍스트로 확인한다.

이전 시도(tools/probe_pagination_walk.py)는 `_walk_paginated_grid` 를 그대로
호출했는데, 그 함수는 완전성 가드가 걸리면 곧바로 예외를 던진다 — 문제는 그
가드가 "중복이 상한(pager_count-1)을 넘는가" 만 확인하고, 5개 중복 행이 각각
어느 페이지 조합에서 나왔는지는 결코 출력하지 않는다는 점이다 (Fix round 1
이후로는 5개 중복 자체는 상한 이내라 예외가 안 나지만, 여전히 어떤 행이
중복인지는 `_walk_paginated_grid` 반환값(dict 병합 후 list)만으로는 알 수
없다 — 중복이었다는 사실 자체가 dict 병합 과정에서 사라진다).

이 스크립트는 `_walk_paginated_grid` 를 호출하지 않는다. 대신 그 함수와 같은
클릭 절차를 이 스크립트 안에서 직접 재현하면서, 페이지별 원본 행 리스트를
전부 보존한 채로 중복을 계산한다 — 어느 행이, 어느 페이지들에서 나왔는지
verbatim 으로 출력한다. try/except 로 전체를 감싸 어떤 예외가 나도 이미 모은
증거를 먼저 출력한 뒤에 종료한다.

정중함: page.goto 1회. 페이지 클릭 사이 400ms 대기(올린 코드와 동일).
"""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

from pipeline import eis_report
from pipeline import olap as olap_mod


def main() -> None:
    url = eis_report.viewer_url(eis_report.REPORTS["유효구인구직"])
    print("viewer url:", url)

    # 페이지별 원본 body(list[list[str]])를 그대로 보존한다 — 중복 판정 전 원형.
    pages_raw: list[list[list[str]]] = []
    header_out: list[str] | None = None
    pager_count = None
    evidence_error: BaseException | None = None

    try:
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

            page.mouse.click(1178, 31)  # 돋보기(검색) 아이콘

            for _ in range(60):
                if page.locator("text=작업 취소").count() == 0:
                    break
                page.wait_for_timeout(1000)
            page.wait_for_timeout(500)

            try:
                page.wait_for_selector(
                    olap_mod._PAGER_CONTAINER_SELECTOR, timeout=olap_mod._PAGER_WAIT_MS
                )
            except Exception:
                pass

            pager_count = page.locator(olap_mod._PAGER_SELECTOR).count()

            grid = page.evaluate(olap_mod._EXTRACT_JS)
            header, *first_body = grid
            header_out = header
            pages_raw.append(first_body)

            if pager_count is not None and pager_count > 1:
                for page_number in range(2, pager_count + 1):
                    olap_mod._click_page(page, page_number)
                    page.wait_for_timeout(olap_mod._PAGE_ADVANCE_WAIT_MS)
                    grid = page.evaluate(olap_mod._EXTRACT_JS)
                    _, *body = grid
                    pages_raw.append(body)

            browser.close()
    except BaseException as exc:  # noqa: BLE001 — 증거를 먼저 찍기 위해 뭐든 잡는다
        evidence_error = exc

    # ---- 여기서부터는 무조건 실행된다 (가드가 무엇을 던지든 상관없이) ----
    print("\n=== 원시 증거 ===")
    print("페이저가 보고한 페이지 수:", pager_count)
    print("헤더:", header_out)
    for i, body in enumerate(pages_raw, start=1):
        print(f"--- {i}페이지: {len(body)}행 ---")
        if body:
            print(f"  첫 행: {body[0]!r}")
            print(f"  마지막 행: {body[-1]!r}")

    all_rows: list[tuple[int, list[str]]] = []
    for page_num, body in enumerate(pages_raw, start=1):
        for row in body:
            if row:
                all_rows.append((page_num, row))

    raw_count = len(all_rows)
    seen_pages: dict[str, list[int]] = {}
    seen_row: dict[str, list[str]] = {}
    for page_num, row in all_rows:
        key = "".join(row)
        seen_pages.setdefault(key, []).append(page_num)
        seen_row[key] = row

    distinct_count = len(seen_pages)
    dup_keys = {k: v for k, v in seen_pages.items() if len(v) > 1}

    print("\n=== 중복 판정 ===")
    print("원시 합계:", raw_count)
    print("고유 개수:", distinct_count)
    print("중복 개수:", raw_count - distinct_count)
    print(f"중복 행 종류 수(서로 다른 key 중 2회 이상 등장): {len(dup_keys)}")

    print("\n=== 중복 행 verbatim (등장 페이지 포함) ===")
    for key, pages_seen in dup_keys.items():
        print(f"  등장 페이지: {pages_seen} | 행: {seen_row[key]!r}")

    if evidence_error is not None:
        print("\n=== 실행 중 예외 발생 (증거는 위에 이미 출력됨) ===", file=sys.stderr)
        print(f"{type(evidence_error).__name__}: {evidence_error}", file=sys.stderr)


if __name__ == "__main__":
    main()
