"""OLAP 뷰어의 좌측 WISE 필드초이서를 조작해 그리드의 행/열 축을 바꾼다.

`tools/probe_field_relocation.py` 와 `tools/probe_series.py` 가 실증한 조작을
그대로 옮긴 것이다 — 새로 발명한 것은 없다. 화면이 요구하는 축((근무지역)시군구
× 직종_중분류 등)은 URL 파라미터로도, 다른 리포트로도 얻을 수 없고 이 드래그
조작으로만 얻는다(경위는 `pipeline/eis.py` 모듈 독스트링의 Task 7 Step 0 절).

**이 파일은 이 저장소에서 가장 깨지기 쉬운 코드다.** 좌측 필드초이서는
DevExtreme 이 아니라 EIS 가 자체 제작한 jQuery-UI 위젯("WISE", 클래스
`wise-area-field`)이라 EIS 가 화면을 손대면 즉시 깨진다. 그래서 이 모듈의
규칙은 하나다 — **깨지면 조용히 다른 축을 수집하는 대신 시끄럽게 실패한다.** 조작이 먹지 않았는데 그냥 넘어가면 파이프라인은
"에러 없이 축만 틀린" 파일을 배포한다. 이 프로젝트에서 가장 나쁜 실패 모양이다.

무엇이 깨지면 어떻게 드러나는가:

  - `#rowAdHocList1…` id 자체가 사라지면 → 인스턴스를 못 좁혀 `LayoutError`.
    인스턴스 **번호**는 상수가 아니라 페이지에서 읽는다(아래 `_instance`) —
    리포트마다 다르기 때문이다.
  - 필드의 `uni_nm` 속성값("(근무지역)시군구" 등)이 바뀌면 → `_drag` 가
    `LayoutError("필드를 못 찾는다")` 를 낸다. 재조회는 하지 않는다.
  - 드래그 자체가 먹지 않으면(마우스 단계 수·드롭 좌표 등) → 재조회 **전에**
    행 영역의 `uni_nm` 목록을 읽어 요청과 대조하므로 `LayoutError` 가 난다
    (그 전에 `PLACE_ATTEMPTS` 만큼 비우고 다시 놓아 본다).
  - 재조회(돋보기) 좌표 클릭이 빗나가면 → 렌더된 그리드의 행 축 설명 셀
    (`.dx-area-description-cell`)이 옛 축 그대로라 `LayoutError` 가 난다.
  - 뷰포트 폭이 실측값(1280)과 다르면 → 좌표 클릭이 애초에 의미가 없으므로
    클릭하기 전에 `LayoutError` 를 낸다.

실측 근거(2026-09-03, 유효구인구직 1·2축 + 경력직이동 3축):
  - 필드를 행 영역의 **상단**(`DROP_AT_TOP`)에 떨어뜨리면 드래그한 순서 그대로
    쌓이고, 렌더된 그리드의 행 축 설명 셀도 같은 "바깥→안쪽" 순서가 된다.
    그래서 이 모듈의 `rows` 인자는 "바깥→안쪽" 축 순서로 받고 그 순서 그대로
    드래그한다.
  - 2026-09-02 실측은 Playwright 기본값대로 영역 **중앙**에 떨어뜨렸고, 그때는
    "나중에 드래그한 필드가 바깥"으로 보였다. 그것은 축이 둘일 때만 맞는
    우연이었다 — 항목이 하나뿐인 영역의 중앙은 그 항목보다 앞이라 앞에
    끼어들기 때문이다. 축이 셋인 경력직이동에서 그 규칙이 깨져(요청
    [시도, 산업, 산업(이전)] → 실제 [산업, 시도, 산업(이전)]) 상단 드롭으로
    바꿨다.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 깨지기 쉬운 상수 — 전부 여기 한 곳에 모은다 (위 독스트링 참고).
# ---------------------------------------------------------------------------
# WISE 위젯 인스턴스 접미사(`_5990` 등)는 **리포트마다 다르다** — 2026-09-03
# 실측: 유효구인구직 `_5990`, 취업건수 `_5987`, 피보험자 `_6248`. 같은 리포트를
# 여러 번 열면 값은 그대로다(세션마다 변하지 않는다). 예전에는 이 번호를 상수로
# 박아 뒀는데, 그러면 유효구인구직 말고는 초기화 클릭이 Playwright 타임아웃으로
# 죽는다(첫 실측 수집이 정확히 그렇게 실패했다). 그래서 열려 있는 페이지에게
# 직접 묻는다 — 추측하지 않고, 못 찾으면 시끄럽게 실패한다.
INSTANCE_PROBE = '[id^="rowAdHocList1_"]'
INSTANCE_RE = re.compile(r"^rowAdHocList1(_\d+)")
IDS_JS = "els => els.map(e => e.id)"
INSTANCE_WAIT_MS = 60_000
FIELD_TEMPLATE = 'li[uni_nm="{field}"][prev-container="allList"]'

# 필드를 영역의 **어디에** 떨어뜨리는가. 실측(2026-09-03): 영역 상단에 놓으면
# 드래그한 순서 그대로 쌓인다. Playwright 의 기본값인 영역 **중앙**에 놓으면
# 이미 있는 항목들 사이로 끼어들어, 축이 셋이 되는 순간 순서가 어긋난다
# (경력직이동에서 요청 [시도, 산업, 산업(이전)] 이 [산업, 시도, 산업(이전)] 이
# 됐다). 2026-09-02 의 "나중에 드래그한 것이 바깥" 규칙은 축이 둘일 때만 맞는
# 우연이었다.
DROP_AT_TOP = {"x": 20, "y": 4}

# 드래그가 이따금 아예 안 먹는다 — 실측(2026-09-03, 피보험자): 요청
# ['(사업장)시군구', '직종_중분류'] 에 시군구 하나만 들어갔다. 34분을 걸어온
# 수집이 그 한 번 때문에 통째로 버려졌다. olap 의 페이지 클릭·창 넘김이 받는
# 보호와 같은 이유·같은 모양이다: 영역을 비우고 다시 놓아 본 뒤, 그래도 안
# 들어가면 그때 실패한다(요청과 다른 축으로는 절대 조회하지 않는다).
PLACE_ATTEMPTS = 2

# 드래그는 Playwright 의 `drag_to` 가 아니라 **마우스를 여러 단계로 옮겨** 한다.
# 실측(2026-09-03, 피보험자 시군구+직종): `drag_to` 는 3/3 실패하고 단계 드래그는
# 3/3 성공했다 — 일시적 실패가 아니라 결정적이다. WISE 는 jQuery-UI 계열이라
# 삽입 위치를 `dragover` 로 계산하는데, `drag_to` 는 중간 mousemove 를 충분히
# 보내지 않아 **항목이 이미 있는 영역**에서 조용히 아무 일도 일어나지 않는다
# (빈 영역에는 어느 방식이든 들어가서, 첫 필드만 놓는 데이터셋에서는 안 드러났다).
DRAG_STEPS = 10
DRAG_STEP_MS = 40
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
    src = source.first.bounding_box()
    dst = page.locator(area).bounding_box()
    if not src or not dst:
        raise LayoutError(
            f"'{field}' 또는 {area} 의 화면 상자를 못 읽는다 — 좌표 드래그를 할 수 없다.")

    start_x, start_y = src["x"] + src["width"] / 2, src["y"] + src["height"] / 2
    end_x, end_y = dst["x"] + DROP_AT_TOP["x"], dst["y"] + DROP_AT_TOP["y"]
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    for step in range(1, DRAG_STEPS + 1):
        page.mouse.move(start_x + (end_x - start_x) * step / DRAG_STEPS,
                        start_y + (end_y - start_y) * step / DRAG_STEPS)
        page.wait_for_timeout(DRAG_STEP_MS)
    page.mouse.up()
    page.wait_for_timeout(DRAG_WAIT_MS)


def _instance(page) -> str:
    """열려 있는 페이지의 WISE 인스턴스 접미사를 읽는다 (예: "_6248").

    같은 접미사를 가진 노드가 여럿이라(`…_5990`, `…_5990_clear`, `…_5990_0`)
    접미사만 뽑아 집합으로 줄인다. 하나로 좁혀지지 않으면 — 없거나 둘 이상이면
    — 어림수를 쓰지 않고 `LayoutError` 를 낸다. 틀린 인스턴스를 골라 조작하면
    "에러 없이 축만 틀린" 그리드를 읽어 가게 되는데, 이 모듈이 막으려는 것이
    바로 그것이다.
    """
    # 좌측 패널은 goto 직후 아직 안 그려져 있을 수 있다. 이 모듈의 전제이므로
    # 여기서 스스로 기다린다 — 부르는 쪽(olap.fetch_grid)은 그리드만 안다.
    # 끝내 안 뜨면 Playwright 의 타임아웃을 그대로 흘리지 않고 무엇이 없는지
    # 말하는 LayoutError 로 바꾼다(이 모듈의 실패는 전부 LayoutError 다).
    try:
        page.wait_for_selector(INSTANCE_PROBE, timeout=INSTANCE_WAIT_MS)
    except Exception as error:      # noqa: BLE001 — 타임아웃까지 기다렸는데 없다
        raise LayoutError(
            f"좌측 WISE 필드초이서가 {INSTANCE_WAIT_MS // 1000}초 안에 안 떴다 "
            f"(셀렉터: {INSTANCE_PROBE}) — 축을 바꿀 수 없으니 조회하지 않는다."
        ) from error
    ids = page.eval_on_selector_all(INSTANCE_PROBE, IDS_JS)
    found = sorted({m.group(1) for i in ids if (m := INSTANCE_RE.match(i or ""))})
    if len(found) != 1:
        raise LayoutError(
            f"WISE 필드초이서 인스턴스를 하나로 못 좁힌다 — 후보 {found} "
            f"(셀렉터: {INSTANCE_PROBE}). 좌측 분석항목 패널이 안 떴거나 "
            "EIS 가 화면 구조를 바꿨을 수 있다.")
    return found[0]


def _areas(page) -> tuple[str, str]:
    """이 페이지의 (행 영역, 열 영역) 셀렉터."""
    instance = _instance(page)
    return f"#rowAdHocList1{instance}", f"#colAdHocList1{instance}"


def _place(page, fields, area: str) -> None:
    """fields(바깥→안쪽)를 area 에 놓는다 — 상단 드롭이라 요청 순서 그대로 드래그한다.

    요청대로 들어갈 때까지 `PLACE_ATTEMPTS` 번 시도한다. 다시 시도할 때는
    영역을 먼저 비운다 — 반쯤 들어간 상태 위에 덧놓으면 순서가 어긋난다.
    """
    fields = list(fields)
    placed: list[str] = []
    for attempt in range(PLACE_ATTEMPTS):
        if attempt:
            page.click(f"{area}_clear")
            page.wait_for_timeout(CLEAR_WAIT_MS)
        for field in fields:
            _drag(page, field, area)
        placed = _area_fields(page, area)
        if placed == fields:
            return
    raise LayoutError(
        f"{area} 에 요청한 축이 들어가지 않았다 — 요청 {fields}, 실제 {placed} "
        f"({PLACE_ATTEMPTS}번 시도). 드래그가 먹지 않았을 수 있다 (재조회하지 않는다).")


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

    row_area, col_area = _areas(page)

    page.click(f"{row_area}_clear")
    page.wait_for_timeout(CLEAR_WAIT_MS)
    page.click(f"{col_area}_clear")
    page.wait_for_timeout(CLEAR_WAIT_MS)

    _place(page, rows, row_area)
    if cols:
        _place(page, cols, col_area)

    _requery(page)

    # 재조회가 실제로 반영됐는지 **렌더된 그리드**에게 묻는다. 필드초이서가
    # 맞더라도 재조회 클릭이 빗나갔으면 그리드는 옛 축 그대로다 — 그 상태로
    # 읽으면 아무 예외 없이 틀린 축의 값을 수집한다.
    rendered = [text for text in page.eval_on_selector_all(DESC_CELLS, DESC_TEXT_JS) if text]
    if rendered != rows:
        raise LayoutError(
            f"재조회 뒤에도 그리드 행 축이 요청과 다르다 — 요청 {rows}, 렌더 {rendered}. "
            f"재조회 좌표 클릭({SEARCH_BUTTON_XY})이 빗나갔거나 조회가 실패했을 수 있다.")
