"""렌더된 EIS OLAP 뷰어 그리드를 읽어 행 리스트로 편다.

경로 확정 (tools/probe_olap.py 로 탐침, 2026-09-01):
  cube/queries.do 의 POST 페이로드 안 "sql" 필드는 AES 로 암호화된 문자열이다
  (crypto-js.min.js + WISE.widget.CrpytoAES256.js 로 세션 키 암복호화). 감싸는
  JSON 봉투는 평문이지만 실데이터는 없고, 실제 그리드는 DevExtreme PivotGrid
  (dx-pivotgrid — 브리프가 가정한 dx-datagrid 가 아니다) 로 클라이언트 렌더링된다.
  따라서 이 모듈은 **DOM 추출** 경로를 쓴다: 렌더된 표를 읽는다.

  보고서 "유효구인구직" (17개 시도 + 총계 = 18행) 은 헤드리스에서도 스크롤 없이
  전량이 DOM 에 이미 존재했다 (dataScroll=Y 는 더 큰 표, 예: 시군구 단위에 대비한
  것으로 보인다). 안전을 위해 fetch_grid 는 그래도 스크롤-누적을 시도한다.
"""
from __future__ import annotations


class OlapExtractionError(RuntimeError):
    """그리드 추출이 불완전하거나 비어 있을 때 낸다.

    이 파이프라인의 원칙: 잘린 그리드를 그럴듯하게 반환하지 않는다. 완전한지
    확신이 없으면 조용히 절반만 반환하는 대신 시끄럽게 실패한다.
    """


_EXTRACT_JS = r"""
() => {
  function expandRow(tr) {
    const cells = Array.from(tr.querySelectorAll('td'));
    const out = [];
    for (const td of cells) {
      const span = parseInt(td.getAttribute('colspan') || '1', 10);
      const text = td.innerText.trim();
      for (let i = 0; i < span; i++) out.push(text);
    }
    return out;
  }

  // 열 머리 (마감년월 x 측정값) — 계층이 있으면 부모 라벨을 붙인다
  const headTrs = Array.from(document.querySelectorAll('thead.dx-pivotgrid-horizontal-headers tr'));
  const headRows = headTrs.map(expandRow);
  let colLabels = [];
  if (headRows.length) {
    const leaf = headRows[headRows.length - 1];
    colLabels = leaf.map((leafText, idx) => {
      const parents = headRows.slice(0, -1).map(r => r[idx]).filter(Boolean);
      return [...parents, leafText].filter(Boolean).join('_');
    });
  }

  // 행 머리 ((지역별)시도 등), DOM 순서 그대로
  const rowLabelEls = Array.from(document.querySelectorAll('tbody.dx-pivotgrid-vertical-headers > tr'));
  const rowLabels = rowLabelEls.map(tr => tr.innerText.trim());

  // 데이터 셀
  const dataTrs = Array.from(document.querySelectorAll('.dx-pivotgrid-area-data table tbody tr'));
  const dataRows = dataTrs.map(tr =>
    Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()));

  const rowDimEl = document.querySelector('.dx-area-description-cell .dx-area-field-content');
  const header = [rowDimEl ? rowDimEl.innerText.trim() : '지역', ...colLabels];

  const body = rowLabels.map((label, i) => [label, ...(dataRows[i] || [])]);
  return [header, ...body];
}
"""


def parse_grid(rows: list[list[str]]) -> list[dict]:
    """첫 행을 헤더로 삼아 [[str]] 를 [dict] 로 편다. (R2: 이 함수의 입력은 항상 list[list[str]])"""
    header, *body = rows
    return [dict(zip(header, row)) for row in body]


def fetch_grid(url: str, *, page, max_scrolls: int = 200) -> list[list[str]]:
    """Playwright page 로 뷰어를 열고 렌더된 PivotGrid 를 읽는다.

    작은 표(예: 시도 단위, 17행)는 스크롤 없이 전량이 DOM 에 있는 것을 확인했다.
    dataScroll=Y 가상화가 걸리는 큰 표(예: 시군구 x 직종, 최대 약 2,450행)에
    대비해 데이터 영역을 끝까지 스크롤하며 고유 행을 누적한다 — 더 늘지 않으면
    멈춘다.

    max_scrolls=200 인 이유: 관측된 행 높이는 19px, 스크롤 한 번은 2000px 이므로
    한 번에 최대 ~105행 분량이 넘어간다. 예상 최대 워크로드(약 2,450행)를 덮으려면
    이론상 ~24회면 충분하지만, 실제 뷰포트/행 높이가 보고서마다 달라질 수 있어
    8배 안전 여유를 두고 브리프가 제시한 200을 그대로 썼다. 캡을 넉넉히 잡아도
    비용이 없다 — 정상적인 경우 행이 늘지 않는 순간 즉시 멈추기 때문이고, 캡이
    부족한 유일한 경우는 이제(아래) 조용히 잘린 결과 대신 예외를 낸다.

    반환은 **완전한 그리드임이 확인된 경우에만** 이뤄진다:
      - max_scrolls 를 다 써도 고유 행 수가 계속 늘면 → OlapExtractionError
      - 컨테이너는 렌더됐지만 데이터 행이 하나도 없으면 → OlapExtractionError
    """
    page.goto(url, wait_until="networkidle", timeout=90_000)
    page.wait_for_selector("div.dx-pivotgrid-area-data", timeout=60_000)
    page.wait_for_timeout(500)

    grid = page.evaluate(_EXTRACT_JS)
    header, *body = grid
    seen: dict[str, list[str]] = {"".join(row): row for row in body if row}

    scroller = page.locator(
        "div.dx-pivotgrid-area-data .dx-scrollable-container"
    ).first

    stabilized = False
    for _ in range(max_scrolls):
        before = len(seen)
        try:
            scroller.evaluate("el => { el.scrollTop += 2000; }")
        except Exception:  # noqa: BLE001 — 스크롤 대상 자체가 없다: 가상화가 없는 작은 표로 간주
            stabilized = True
            break
        page.wait_for_timeout(200)
        grid = page.evaluate(_EXTRACT_JS)
        header, *body = grid
        for row in body:
            if row:
                seen["".join(row)] = row
        if len(seen) == before:
            stabilized = True
            break

    if not stabilized:
        raise OlapExtractionError(
            f"그리드가 안정화되지 않았다 — max_scrolls={max_scrolls} 를 다 써도 "
            f"행이 계속 늘어남 (수집된 고유 행 {len(seen)}개, 캡 {max_scrolls}회 도달). "
            "잘렸을 수 있는 그리드를 반환하지 않는다 — max_scrolls 를 늘리거나 "
            "가상화 동작을 다시 확인하라."
        )

    if not seen:
        raise OlapExtractionError(
            "그리드 컨테이너는 렌더됐지만 데이터 행이 하나도 없다 (헤더만 존재) — "
            "느린 렌더링이거나 필터/레이아웃이 잘못됐을 수 있다."
        )

    return [header, *seen.values()]


def fetch_and_parse_grid(url: str, *, browser, max_scrolls: int = 200) -> list[dict]:
    """뷰어를 열어 그리드를 읽고 바로 dict 리스트로 편다 (fetch_grid + parse_grid)."""
    page = browser.new_page()
    try:
        rows = fetch_grid(url, page=page, max_scrolls=max_scrolls)
    finally:
        page.close()
    return parse_grid(rows)
