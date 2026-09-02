"""OLAP 뷰어의 좌측 WISE 필드초이서를 조작해 그리드의 행/열 축을 바꾼다.

`tools/probe_field_relocation.py` 와 `tools/probe_series.py` 가 실증한 조작을
그대로 옮긴 것이다 — 새로 발명한 것은 없다. 화면이 요구하는 축((근무지역)시군구
× 직종_중분류 등)은 URL 파라미터로도, 다른 리포트로도 얻을 수 없고 이 드래그
조작으로만 얻는다(경위는 `pipeline/eis.py` 모듈 독스트링의 Task 7 Step 0 절).

**이 파일은 이 저장소에서 가장 깨지기 쉬운 코드다.** 좌측 필드초이서는
DevExtreme 이 아니라 EIS 가 자체 제작한 jQuery-UI 위젯("WISE", 클래스
`wise-area-field`, 인스턴스 id 접미사 `_5990`)이라 EIS 가 화면을 손대면 즉시
깨진다. 그래서 이 모듈의 규칙은 하나다 — **깨지면 조용히 다른 축을 수집하는
대신 시끄럽게 실패한다.** 조작이 먹지 않았는데 그냥 넘어가면 파이프라인은
"에러 없이 축만 틀린" 파일을 배포한다. 이 프로젝트에서 가장 나쁜 실패 모양이다.

무엇이 깨지면 어떻게 드러나는가:

  - `_5990` 인스턴스 번호나 `#rowAdHocList1…` id 가 바뀌면 → 초기화 클릭이
    Playwright 타임아웃으로 죽는다(예외).
  - 필드의 `uni_nm` 속성값("(근무지역)시군구" 등)이 바뀌면 → `_drag` 가
    `LayoutError("필드를 못 찾는다")` 를 낸다. 재조회는 하지 않는다.
  - 드래그 자체가 먹지 않으면(HTML5 DnD 동작 변경 등) → 재조회 **전에**
    행 영역의 `uni_nm` 목록을 읽어 요청과 대조하므로 `LayoutError` 가 난다.
  - 재조회(돋보기) 좌표 클릭이 빗나가면 → 렌더된 그리드의 행 축 설명 셀
    (`.dx-area-description-cell`)이 옛 축 그대로라 `LayoutError` 가 난다.
  - 뷰포트 폭이 실측값(1280)과 다르면 → 좌표 클릭이 애초에 의미가 없으므로
    클릭하기 전에 `LayoutError` 를 낸다.

실측 근거(2026-09-02, 유효구인구직 menuId=020010020 뷰어):
  - 행 영역에 [시군구, 직종] 순으로 드래그하면 `#rowAdHocList1_5990` 의
    `uni_nm` 은 `['직종_중분류', None, …, '(근무지역)시군구', None, …]` 이 되고
    그리드는 직종_중분류(바깥) × (근무지역)시군구(안쪽)로 렌더된다. 즉
    **나중에 드래그한 필드가 바깥쪽**이다. 그래서 이 모듈의 `rows` 인자는
    "바깥→안쪽" 축 순서로 받고 드래그는 그 역순으로 한다 — 부르는 쪽이
    드래그 순서를 뒤집어 생각하지 않게 하려는 것이다.
  - 렌더된 그리드의 행 축 설명 셀도 같은 "바깥→안쪽" 순서다
    (`['직종_중분류', '(근무지역)시군구']`).
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# 깨지기 쉬운 상수 — 전부 여기 한 곳에 모은다 (위 독스트링 참고).
# ---------------------------------------------------------------------------
WISE_INSTANCE = "_5990"
ROW_AREA = f"#rowAdHocList1{WISE_INSTANCE}"
COL_AREA = f"#colAdHocList1{WISE_INSTANCE}"
ROW_CLEAR = f"{ROW_AREA}_clear"
COL_CLEAR = f"{COL_AREA}_clear"
FIELD_TEMPLATE = 'li[uni_nm="{field}"][prev-container="allList"]'
AREA_ITEMS_JS = "els => els.map(e => e.getAttribute('uni_nm'))"
DESC_TEXT_JS = "els => els.map(e => e.innerText.trim())"

# 렌더된 그리드가 실제로 어떤 행 축으로 그려졌는지 알려주는 좌상단 설명 셀.
# 드래그가 아니라 **결과**를 보는 유일한 창이라 재조회 검증에 쓴다.
DESC_CELLS = ".dx-area-description-cell .dx-area-field-content"

# 돋보기(검색) 아이콘 좌표. 아이콘 자체는 크기 0 래퍼라 locator 클릭이
# "element is not visible" 로 실패한다 — probe 스크립트들이 쓴 좌표를 그대로
# 옮겼다. 좌표는 뷰포트 폭에 매여 있으므로 폭을 먼저 확인한다.
SEARCH_BUTTON_XY = (1178, 31)
EXPECTED_VIEWPORT_WIDTH = 1280

# 재조회 중에는 "작업 취소" 버튼(로딩 스피너)이 떠 있다.
#
# 실측(2026-09-02) 교정: 이 노드는 **항상 DOM 에 있고 보이기/숨기기로만
# 토글된다.** probe 스크립트들이 쓰던 `locator(...).count() == 0` 조건은 그래서
# 영원히 참이 되지 않았고, 그 루프는 사실 매번 60초를 다 기다린 뒤 그냥
# 빠져나온 것이었다(그래서 "동작하는 것처럼" 보였다). 여기서는 존재가 아니라
# **가시성**을 본다 — 실측상 이 리포트의 재조회는 5초 안에 끝난다.
BUSY_TEXT = "작업 취소"
BUSY_POLL_MS = 1_000
BUSY_MAX_POLLS = 120
# 클릭 직후에는 스피너가 아직 안 떴을 수 있다 — 뜨기도 전에 "끝났다"고
# 판단하지 않도록 짧게 기다린 뒤에 폴링을 시작한다.
BUSY_APPEAR_MS = 2_000

# 위젯이 DOM 을 갱신할 짬 (probe 스크립트들이 쓴 값 그대로).
CLEAR_WAIT_MS = 300
DRAG_WAIT_MS = 500
SETTLE_MS = 500


class LayoutError(RuntimeError):
    """축 조작이 요청대로 되지 않았을 때 낸다.

    조용히 넘어가면 파이프라인이 "에러 없이 축만 틀린" 파일을 배포한다.
    """


def _area_fields(page, area: str) -> list[str]:
    """영역 안에 실제로 들어 있는 필드 이름을 바깥→안쪽 순서로 읽는다.

    실측상 영역 li 사이에는 `uni_nm` 이 없는 자리표시자(None)가 섞여 있다.
    """
    items = page.eval_on_selector_all(f"{area} li", AREA_ITEMS_JS)
    return [item for item in items if item]


def _drag(page, field: str, area: str) -> None:
    selector = FIELD_TEMPLATE.format(field=field)
    source = page.locator(selector)
    if source.count() == 0:
        raise LayoutError(
            f"필드 '{field}' 를 좌측 분석항목 목록에서 못 찾는다 — uni_nm 속성값이 "
            f"바뀌었을 수 있다 (셀렉터: {selector})")
    source.first.scroll_into_view_if_needed()
    source.first.drag_to(page.locator(area))
    page.wait_for_timeout(DRAG_WAIT_MS)


def _place(page, fields, area: str) -> None:
    """fields(바깥→안쪽)를 area 에 놓는다 — 나중에 놓은 것이 바깥이라 역순으로 드래그한다."""
    for field in reversed(list(fields)):
        _drag(page, field, area)
    placed = _area_fields(page, area)
    if placed != list(fields):
        raise LayoutError(
            f"{area} 에 요청한 축이 들어가지 않았다 — 요청 {list(fields)}, 실제 {placed}. "
            "드래그가 먹지 않았을 수 있다 (재조회하지 않는다).")


def _requery(page) -> None:
    """돋보기(검색)를 눌러 재조회하고 로딩 스피너가 사라질 때까지 기다린다."""
    viewport = page.viewport_size or {}
    width = viewport.get("width")
    if width != EXPECTED_VIEWPORT_WIDTH:
        raise LayoutError(
            f"뷰포트 폭이 {width} 다 — 재조회는 실측 좌표 {SEARCH_BUTTON_XY} 클릭에 "
            f"기대므로 폭이 {EXPECTED_VIEWPORT_WIDTH} 가 아니면 엉뚱한 곳을 누른다.")
    page.mouse.click(*SEARCH_BUTTON_XY)
    page.wait_for_timeout(BUSY_APPEAR_MS)
    busy = page.locator(f"text={BUSY_TEXT}")
    for _ in range(BUSY_MAX_POLLS):
        if busy.count() == 0 or not busy.first.is_visible():
            page.wait_for_timeout(SETTLE_MS)
            return
        page.wait_for_timeout(BUSY_POLL_MS)
    raise LayoutError(
        f"재조회가 {BUSY_MAX_POLLS * BUSY_POLL_MS // 1000}초 안에 안 끝났다 "
        f"('{BUSY_TEXT}' 가 계속 떠 있다) — 잘렸을 수 있는 그리드를 읽지 않는다.")


def set_layout(page, *, rows, cols=()) -> None:
    """행/열 축을 rows·cols 로 바꾼다. rows·cols 는 **바깥→안쪽** 순서다.

    초기화 → 드래그 → (드래그 검증) → 재조회 → (렌더 결과 검증) 순으로 돈다.
    어느 단계든 요청대로 되지 않으면 `LayoutError` 를 낸다 — 조용히 다른 축의
    그리드를 읽어 가는 경로는 하나도 없다.
    """
    rows = list(rows)
    cols = list(cols)
    if not rows:
        raise LayoutError("행 축을 비운 채로는 조회할 수 없다")

    page.click(ROW_CLEAR)
    page.wait_for_timeout(CLEAR_WAIT_MS)
    page.click(COL_CLEAR)
    page.wait_for_timeout(CLEAR_WAIT_MS)

    _place(page, rows, ROW_AREA)
    if cols:
        _place(page, cols, COL_AREA)

    _requery(page)

    # 재조회가 실제로 반영됐는지 **렌더된 그리드**에게 묻는다. 필드초이서가
    # 맞더라도 재조회 클릭이 빗나갔으면 그리드는 옛 축 그대로다 — 그 상태로
    # 읽으면 아무 예외 없이 틀린 축의 값을 수집한다.
    rendered = [text for text in page.eval_on_selector_all(DESC_CELLS, DESC_TEXT_JS) if text]
    if rendered != rows:
        raise LayoutError(
            f"재조회 뒤에도 그리드 행 축이 요청과 다르다 — 요청 {rows}, 렌더 {rendered}. "
            f"재조회 좌표 클릭({SEARCH_BUTTON_XY})이 빗나갔거나 조회가 실패했을 수 있다.")
