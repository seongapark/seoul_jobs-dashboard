"""OLAP 추출 경로를 확정하기 위한 일회성 탐침.

세 가지를 확인한다.
 1) cube/queries.do 응답이 평문 JSON 인가, 암호문인가
 2) 렌더된 그리드를 DOM 에서 읽을 수 있는가 (dataScroll=Y 가상화 여부)
 3) 다운로드 버튼이 헤드리스에서 파일을 떨구는가

결과를 stdout 에 적고 cube 응답 하나를 tests/fixtures/olap_grid.json 에 남긴다.
정중함 원칙: 이 스크립트는 뷰어를 한 번만 연다 (page.goto 1회).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from pipeline import eis_report

OUT = Path(__file__).resolve().parents[1] / "tests/fixtures/olap_grid.json"


def main(menu_id: str) -> None:
    url = eis_report.viewer_url(menu_id)
    print("== viewer url:", url)
    captured: list[dict] = []
    other_calls: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(accept_downloads=True)

        def on_response(response):
            if "cube/queries.do" in response.url:
                try:
                    body = response.text()
                except Exception as exc:  # noqa: BLE001
                    body = f"<본문을 읽을 수 없음: {exc}>"
                captured.append({"url": response.url, "status": response.status, "body": body})
            elif any(k in response.url for k in ("getSecretKey.do", "getReportType.do", "queries.do")):
                other_calls.append(f"{response.status} {response.url}")

        page.on("response", on_response)

        # --- 단 한 번의 goto ---
        page.goto(url, wait_until="networkidle", timeout=90_000)
        page.wait_for_timeout(4000)

        print("\n---- (a) cube/queries.do 응답 형태 ----")
        print("== cube 응답 수:", len(captured))
        print("== 그 밖에 관측된 호출:")
        for c in other_calls:
            print("   ", c)
        is_plain_json = False
        if captured:
            first = captured[0]
            head = first["body"][:300]
            print("== 응답 상태코드:", first["status"])
            print("== 응답 머리 300자:", head)
            stripped = first["body"].lstrip()
            is_plain_json = stripped.startswith(("{", "["))
            print("== 평문 JSON 인가:", is_plain_json)
            if is_plain_json:
                try:
                    parsed = json.loads(first["body"])
                    print("== JSON 파싱 성공, 최상위 키/타입:",
                          list(parsed.keys()) if isinstance(parsed, dict) else type(parsed))
                except Exception as exc:  # noqa: BLE001
                    print("== JSON 파싱 실패:", exc)
                    is_plain_json = False
            OUT.write_text(json.dumps(first, ensure_ascii=False, indent=1), encoding="utf-8")
            print("== 응답 저장:", OUT)
        else:
            print("== cube/queries.do 응답이 하나도 관측되지 않음")

        print("\n---- (b) DOM 그리드 판독 ----")
        # 실제로 렌더되는 위젯은 dx-datagrid 가 아니라 DevExtreme PivotGrid
        # (dx-pivotgrid) 였다 — 최초 탐침에서 dx-datagrid-rowsview 셀렉터가
        # 타임아웃난 뒤 tools/probe_olap2.py 로 스크린샷/HTML 을 떠서 확인함.
        try:
            page.wait_for_selector("div.dx-pivotgrid-area-data", timeout=30_000)
            grid_found = True
        except Exception as exc:  # noqa: BLE001
            grid_found = False
            print("== dx-pivotgrid-area-data 셀렉터를 찾지 못함:", exc)

        dom_rows: list[list[str]] = []
        if grid_found:
            from pipeline import olap as olap_mod

            grid = page.evaluate(olap_mod._EXTRACT_JS)
            header, *body = grid
            dom_rows = body
            print("== 열 머리:", header)
            print("== 행 수 (스크롤 없이, 같은 page 재사용 — 두 번째 goto 는 하지 않는다):", len(body))
            print("== 표본 (앞 5행):")
            for r in dom_rows[:5]:
                print("   ", r)

        text = page.inner_text("body")
        print("== body 전체 글자 수:", len(text))

        print("\n---- (c) 다운로드 버튼 (헤드리스) ----")
        download_ok = False
        try:
            candidates = page.locator("text=다운로드")
            count = candidates.count()
            print("== '다운로드' 텍스트를 포함한 요소 수:", count)
            if count == 0:
                candidates = page.locator("[title*='다운로드'], [aria-label*='다운로드']")
                count = candidates.count()
                print("== title/aria-label '다운로드' 요소 수:", count)
            if count > 0:
                try:
                    with page.expect_download(timeout=8_000) as dl_info:
                        candidates.first.click(timeout=8_000)
                    download = dl_info.value
                    print("== 다운로드 발생:", download.suggested_filename)
                    download_ok = True
                except Exception as exc:  # noqa: BLE001
                    print("== 보통 클릭 실패 (숨겨진 요소일 수 있음):", exc)
                    print("== force 클릭으로 재시도")
                    with page.expect_download(timeout=8_000) as dl_info:
                        candidates.first.click(force=True, timeout=8_000)
                    download = dl_info.value
                    print("== force 클릭으로 다운로드 발생:", download.suggested_filename)
                    download_ok = True
            else:
                print("== 다운로드 버튼을 찾지 못함")
        except Exception as exc:  # noqa: BLE001
            print("== 다운로드 시도 실패:", exc)

        print("\n---- 요약 ----")
        print("(a) 평문 JSON:", is_plain_json)
        print("(b) DOM 판독 가능 + 전량 존재:", grid_found, "/", len(dom_rows), "행")
        print("(c) 헤드리스 다운로드 성공:", download_ok)

        browser.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else eis_report.REPORTS["유효구인구직"])
