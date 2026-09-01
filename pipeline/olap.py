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

Task 7 Step 0 탐침 추가 (2026-09-01, tools/probe_flat_sigungu.py 등):
  위 가정은 절반만 맞았다. dataScroll=Y 무한 스크롤은 행이 적어 원래 스크롤이
  필요 없던 표(시도 17행)에서만 확인됐을 뿐, 실제로 행이 많은 표는 스크롤이
  아니라 **DevExtreme 데이터그리드 스타일 페이저**(`.dx-datagrid-pager`,
  `.dx-pages` 안에 `.dx-page` 들)로 나뉘어 렌더된다. (지역별)시군구 단독(중첩
  없이, ~250행)만 놓아도 페이지 6개로 쪼개져 최초 로드에는 50행만 DOM 에 있다.
  이 상태에서 `.dx-pivotgrid-area-data .dx-scrollable-container` 를 스크롤해도
  더 이상 새 행이 나오지 않으므로 (같은 페이지 안에서 스크롤이 끝까지 갔을 뿐,
  다음 페이지로 안 넘어간다) 루프는 "안정화됐다"고 착각하고 50행짜리 그리드를
  아무 예외 없이 반환한다 — 이 모듈이 막으려던 바로 그 "잘렸는데 그럴듯한 결과"
  다. 그래서 스크롤을 시도하기 전에 페이저 존재를 먼저 확인해 시끄럽게 실패
  시킨다(`OlapPaginationError`). 페이지네이션을 실제로 넘겨가며 누적하는 로직은
  아직 없다 — 후속 작업.

Task 7b (2026-09-01): 그 후속 작업 — 페이지네이션 누적을 구현했다. 페이저가
  2개 이상이면 더 이상 즉시 실패하지 않는다. 대신 1페이지째는 이미 읽어둔 채로
  `.dx-datagrid-pager .dx-page` 버튼을 2페이지부터 순서대로 클릭해 걷는다
  (`_walk_paginated_grid`). 실패는 여전히 시끄럽다 — 페이지 클릭이 행을 못
  바꾸면(`OlapPageWalkError`), 어느 페이지가 데이터 행을 하나도 안 주면
  (`OlapExtractionError`), 마지막이 아닌 페이지가 `_PAGE_SIZE` 와 다르면, 또는
  다 걷은 뒤 고유 행 총수가 페이저가 암시하는 총합과 안 맞으면 모두
  `OlapPageWalkError` 를 낸다. 잘린 그리드를 반환하는 대신 예외를 낸다는 원칙은
  그대로다.
"""
from __future__ import annotations

# 실측: EIS 데이터그리드 페이저의 페이지당 행 수 (tools/probe_flat_sigungu.py,
# (지역별)시군구 단독 축 ~250행 → 페이지 6개 x 50행/페이지).
_PAGE_SIZE = 50
_PAGER_CONTAINER_SELECTOR = ".dx-datagrid-pager"
_PAGER_SELECTOR = f"{_PAGER_CONTAINER_SELECTOR} .dx-page"
# 페이저가 진짜 있으면 보통 이 안에 뜬다. 없으면 이 시간을 다 기다린 뒤에야
# "없다"고 판단한다 — 고정 500ms 대기보다 느릴 수 있지만, 늦게 뜨는 페이저를
# "없다"고 오판해 조용히 첫 페이지만 반환하는 쪽보다 안전 쪽으로 실패한다.
_PAGER_WAIT_MS = 5_000


class OlapExtractionError(RuntimeError):
    """그리드 추출이 불완전하거나 비어 있을 때 낸다.

    이 파이프라인의 원칙: 잘린 그리드를 그럴듯하게 반환하지 않는다. 완전한지
    확신이 없으면 조용히 절반만 반환하는 대신 시끄럽게 실패한다.
    """


class OlapPaginationError(OlapExtractionError):
    """그리드가 스크롤이 아니라 (다중) 페이지로 나뉘어 있을 때 낸다.

    fetch_grid 의 스크롤-누적 루프는 페이지네이션을 넘기지 못한다 — 같은 페이지
    안에서 스크롤이 끝까지 가면 "더 안 늘어난다"며 안정화된 것으로 착각해 첫
    페이지만 조용히 반환한다. 페이지가 2개 이상이면 스크롤을 시도하기도 전에
    이 예외를 낸다. 페이지네이션 누적은 아직 구현되지 않았다.
    """


class OlapPageWalkError(OlapPaginationError):
    """다중 페이지 그리드를 누적하는 도중 무언가 신뢰할 수 없을 때 낸다 (Task 7b).

    다음 중 하나면 이 예외를 낸다 — 모두 "잘렸을 수 있는데 그럴듯한 결과"를
    막기 위함이다:
      - 페이지 버튼을 클릭해 다음 페이지로 이동을 시도했는데 렌더된 행이 이전
        페이지와 똑같다 (클릭이 페이지를 못 넘겼을 가능성).
      - 마지막 페이지가 아닌 페이지가 본문 행 수 `_PAGE_SIZE` 와 다르다.
      - 전 페이지를 다 걸은 뒤 고유 행 총수가 페이저가 암시하는 총합
        ((페이지수-1) x `_PAGE_SIZE` + 마지막 페이지 행 수) 과 다르다.
    """


# 페이지 이동 사이 짧은 대기 (정중함) — 스크롤 폴링 대기(200ms)와 같은 자릿수.
_PAGE_ADVANCE_WAIT_MS = 400


def _click_page(page, page_number: int) -> None:
    """`.dx-datagrid-pager` 안 1-based page_number 번째 페이지 버튼을 클릭한다."""
    page.locator(_PAGER_SELECTOR).nth(page_number - 1).click()


def _walk_paginated_grid(
    page, *, header: list[str], first_body: list[list[str]], pager_count: int
) -> list[list[str]]:
    """`.dx-datagrid-pager` 페이지 버튼을 순서대로 눌러가며 전 페이지를 누적한다.

    fetch_grid 가 이미 1페이지째를 읽어(header, first_body) pager_count>1 임을
    확인한 뒤에만 호출한다. 페이지 사이 `_PAGE_ADVANCE_WAIT_MS` 만큼 쉰다(정중함).

    반환은 두 가지 독립된 기준으로 완전성이 확인된 경우에만:
      1. 페이지 이동마다 실제로 행이 바뀌었는가 (안 바뀌면 클릭이 안 먹은 것).
      2. 마지막 페이지를 제외한 모든 페이지가 정확히 `_PAGE_SIZE` 행인가, 그리고
         다 걷은 뒤 고유 행 총수가 페이저가 "암시하는" 총합
         ((pager_count-1) x `_PAGE_SIZE` + 마지막 페이지 행 수) 과 정확히 같은가.
    어느 쪽이든 안 맞으면 조용히 넘어가지 않고 예외를 낸다.
    """
    if pager_count < 2:
        # 호출부(fetch_grid)가 이미 pager_count>1 일 때만 부르므로 정상 경로에서는
        # 닿지 않는다 — 방어적 불변식이다. 그래도 페이지 수를 못 정한 채 여기
        # 들어오면 조용히 진행하는 대신 시끄럽게 실패한다.
        raise OlapPageWalkError(
            f"페이지 수를 알아낼 수 없다 (pager_count={pager_count}) — "
            f"{_PAGER_SELECTOR} 로 페이지 버튼을 둘 이상 세지 못했다."
        )

    if not first_body:
        raise OlapExtractionError(
            "1페이지에 데이터 행이 하나도 없다 (헤더만 존재) — "
            "느린 렌더링이거나 필터/레이아웃이 잘못됐을 수 있다."
        )

    seen: dict[str, list[str]] = {}
    for row in first_body:
        if row:
            seen["".join(row)] = row

    prev_body = first_body
    page_sizes = [len(first_body)]

    for page_number in range(2, pager_count + 1):
        _click_page(page, page_number)
        page.wait_for_timeout(_PAGE_ADVANCE_WAIT_MS)

        grid = page.evaluate(_EXTRACT_JS)
        _, *body = grid

        if not body:
            raise OlapExtractionError(
                f"{page_number}페이지가 데이터 행을 하나도 반환하지 않았다 — "
                "잘렸을 수 있는 그리드를 반환하지 않는다."
            )

        if body == prev_body:
            raise OlapPageWalkError(
                f"{page_number}페이지로 이동을 시도했지만 렌더된 행이 이전 "
                f"페이지와 똑같다 (총 {pager_count}페이지 중) — "
                f"{_PAGER_SELECTOR} 클릭이 페이지를 못 넘겼을 수 있다."
            )

        page_sizes.append(len(body))
        for row in body:
            if row:
                seen["".join(row)] = row
        prev_body = body

    for i, size in enumerate(page_sizes[:-1], start=1):
        if size != _PAGE_SIZE:
            raise OlapPageWalkError(
                f"{i}페이지가 {size}행을 반환했다 — 마지막 페이지가 아닌데 "
                f"페이지 크기({_PAGE_SIZE})와 다르다. 페이지가 잘못 넘어갔을 "
                "수 있다."
            )

    implied_total = (pager_count - 1) * _PAGE_SIZE + page_sizes[-1]
    if len(seen) != implied_total:
        raise OlapPageWalkError(
            f"누적 고유 행 수({len(seen)})가 페이저가 암시하는 총합"
            f"({implied_total} = 페이지 {pager_count}개 중 {pager_count - 1}개 x "
            f"{_PAGE_SIZE}행 + 마지막 페이지 {page_sizes[-1]}행)과 다르다 — "
            "일부 행이 중복 판정으로 소실됐거나 페이지가 잘못 넘어갔을 수 있다."
        )

    return [header, *seen.values()]


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
      - 그리드가 스크롤이 아니라 페이지네이션으로 나뉘어 있으면(Task 7 Step 0
        탐침: 행이 많은 레이아웃은 무한 스크롤이 아니라 `.dx-datagrid-pager`
        페이저를 쓴다 — 스크롤 누적은 첫 페이지만 본다) → 스크롤 대신
        `_walk_paginated_grid` 로 페이지 버튼을 순서대로 눌러가며 전 페이지를
        누적한다(Task 7b). 페이저 존재는 두 가지 독립된 방식으로 확인한다:
        (1) 페이저 컨테이너 자체를 명시적으로 기다린 뒤 세고, (2) 페이저가 안
        잡혔더라도 본문 행 수가 페이지 크기의 정확한 배수면 — 우연이라기엔
        너무 딱 맞아떨어지므로 — 탐지 실패로 보고 실패한다(모듈 수준 단일
        페이지로 오판하지 않기 위함). 타이밍에 기대는 건 (1)뿐이고, (2)는
        시간과 무관한 교차검증이다. 페이지 걷기 자체가 실패하면(클릭이 안
        먹거나, 어느 페이지가 비었거나, 누적 총수가 안 맞으면)
        `OlapPageWalkError`/`OlapExtractionError` 를 낸다 (`_walk_paginated_grid`
        docstring 참고).
      - max_scrolls 를 다 써도 고유 행 수가 계속 늘면 → OlapExtractionError
      - 컨테이너는 렌더됐지만 데이터 행이 하나도 없으면 → OlapExtractionError
    """
    page.goto(url, wait_until="networkidle", timeout=90_000)
    page.wait_for_selector("div.dx-pivotgrid-area-data", timeout=60_000)

    # 페이저는 데이터 영역보다 늦게 뜰 수 있다. 고정 시간만 대기한 뒤 바로
    # 세면, 진짜 다중 페이지 그리드도 "아직 안 떴을 뿐"인데 "없다"고 오판해
    # 스크롤 누적으로 새 버려 첫 페이지만 조용히 반환할 위험이 있다 — 이
    # 모듈이 막으려는 바로 그 실수다. 그래서 페이저 컨테이너 자체를 명시적
    # 타임아웃으로 기다린다: 그 안에 뜨면 잡고, 끝까지 안 뜨면 그게 "없다"는
    # 증거다 (추측이 아니다).
    try:
        page.wait_for_selector(_PAGER_CONTAINER_SELECTOR, timeout=_PAGER_WAIT_MS)
    except Exception:  # noqa: BLE001 — 타임아웃까지 기다렸는데도 없다 = 진짜 없다
        pass

    pager_count = page.locator(_PAGER_SELECTOR).count()

    grid = page.evaluate(_EXTRACT_JS)
    header, *body = grid

    if pager_count > 1:
        # 스크롤 누적으로는 첫 페이지 분량만 보인다 — 페이지 버튼을 순서대로
        # 눌러가며 전 페이지를 누적한다(Task 7b). 완전성이 확인되지 않으면
        # _walk_paginated_grid 가 알아서 시끄럽게 실패한다.
        return _walk_paginated_grid(
            page, header=header, first_body=body, pager_count=pager_count
        )

    # 시간에 기대지 않는 교차검증: 페이저를 못 찾았는데도 본문 행 수가 정확히
    # 페이지 크기(_PAGE_SIZE)의 배수면, 데이터가 우연히 페이지 경계에서 끝났을
    # 가능성보다 페이저 탐지 자체(셀렉터 변경 등)가 실패했을 가능성이 훨씬
    # 크다 — 역시 조용히 넘어가지 않는다.
    if pager_count <= 1 and len(body) > 0 and len(body) % _PAGE_SIZE == 0:
        raise OlapPaginationError(
            f"페이저를 못 찾았는데 본문이 정확히 {_PAGE_SIZE}행 배수({len(body)}행)다 — "
            f"우연히 페이지 경계에서 끝났다고 보기보다 페이저 탐지 실패로 본다. "
            f"페이저 셀렉터({_PAGER_SELECTOR})가 바뀌었는지 확인하라."
        )

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
