"""pipeline.layout 테스트 — 가짜 page 스텁으로 드래그 조작 순서와 실패를 검증한다.
네트워크·브라우저 없음 (tests/test_olap_parse.py 의 스텁 스타일을 따른다)."""
import collections

import pytest

from pipeline import layout


def _field_of(selector: str) -> str:
    return selector.split('uni_nm="')[1].split('"')[0]


class _FakeLocator:
    def __init__(self, page, selector):
        self._page = page
        self._selector = selector

    @property
    def first(self):
        return self

    def count(self):
        return self._page.field_counts.get(self._selector, 1)

    def scroll_into_view_if_needed(self):
        self._page.calls.append(("scroll", self._selector))

    def drag_to(self, target, target_position=None):
        self._page.calls.append(("drag", self._selector, target._selector, target_position))
        # 실측(2026-09-03, 경력직이동 3축 + 유효구인구직 1·2축): 영역 **상단**에
        # 떨어뜨리면 드래그한 순서 그대로 쌓인다. 중앙에 떨어뜨리면 항목이 둘일 때
        # 가운데로 끼어들어 3축에서 순서가 어긋난다 — 그래서 상단 드롭을 요구한다.
        if target_position != layout.DROP_AT_TOP:
            raise AssertionError(
                f"영역 중앙 드롭은 순서를 보장하지 않는다 (target_position={target_position})")
        field = _field_of(self._selector)
        # 실측(2026-09-03, 피보험자): 드래그가 이따금 아예 안 먹는다.
        if self._page.drops_to_ignore.get(field, 0) > 0:
            self._page.drops_to_ignore[field] -= 1
            return
        self._page.dragged[target._selector].append(field)


class _BusyLocator:
    """실측: '작업 취소' 노드는 **항상 DOM 에 있고** 보이기/숨기기로만 토글된다."""

    def __init__(self, visible):
        self._visible = visible

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def is_visible(self):
        return self._visible


class _FakePage:
    """layout.set_layout 이 실제로 쓰는 page 인터페이스만 흉내낸다.

    area_items: 필드초이서 행 영역이 돌려줄 uni_nm 목록. None 이면 "나중에
      드래그한 필드가 바깥쪽"이라는 실측 동작을 흉내낸다(= 드래그 역순).
    desc_cells: 재조회 뒤 렌더된 그리드의 행 축 설명 셀. None 이면 정상 동작.
    """

    def __init__(self, *, area_items=None, desc_cells=None, field_counts=None,
                 viewport_width=layout.EXPECTED_VIEWPORT_WIDTH, busy_forever=False,
                 instance="_5990", drops_to_ignore=None):
        self.calls = []
        self.instance = instance
        # 페이지가 돌려줄 id 목록 — 필드초이서가 아예 없는 상황도 흉내낼 수 있게
        # 테스트가 갈아끼울 수 있다.
        self.instance_ids = None
        # {필드 이름: 무시할 드래그 횟수} — "드래그가 이따금 안 먹는다" 재현용.
        self.drops_to_ignore = dict(drops_to_ignore or {})
        self.row_area = f"#rowAdHocList1{instance}"
        self.col_area = f"#colAdHocList1{instance}"
        self.row_clear = f"{self.row_area}_clear"
        self.col_clear = f"{self.col_area}_clear"
        # 실제 코드가 어떤 인스턴스를 골랐든 기록한다 — 하드코딩된 번호를 쓰면
        # 이 페이지의 번호와 달라지고, 그 차이가 테스트에서 드러난다.
        self.dragged = collections.defaultdict(list)
        self._area_items = area_items
        self._desc_cells = desc_cells
        self.field_counts = field_counts or {}
        self.viewport_size = {"width": viewport_width, "height": 720}
        self._busy_forever = busy_forever

    def click(self, selector):
        self.calls.append(("click", selector))
        if selector.endswith("_clear"):
            self.dragged[selector[: -len("_clear")]] = []

    def wait_for_timeout(self, ms):
        pass

    def wait_for_selector(self, selector, **kwargs):
        """set_layout 은 자기 전제(좌측 필드초이서)를 스스로 기다린다.

        instance_ids 를 빈 목록으로 준 테스트는 "패널이 끝내 안 뜬다"를 뜻하므로
        실제 Playwright 처럼 타임아웃을 낸다.
        """
        self.calls.append(("wait", selector))
        if selector == layout.INSTANCE_PROBE and self.instance_ids == []:
            raise TimeoutError(f"타임아웃 (가짜): {selector}")

    def locator(self, selector):
        if selector == f"text={layout.BUSY_TEXT}":
            return _BusyLocator(self._busy_forever)
        return _FakeLocator(self, selector)

    def eval_on_selector_all(self, selector, js):
        if selector == layout.INSTANCE_PROBE:
            if self.instance_ids is not None:
                return self.instance_ids
            # 실측: 같은 접미사를 가진 노드가 여럿이다(영역 자체, _clear, _0 …).
            return [f"rowAdHocList1{self.instance}",
                    f"rowAdHocList1{self.instance}_clear",
                    f"rowAdHocList1{self.instance}_0"]
        if selector.startswith("#rowAdHocList1"):
            area = selector.split(" ")[0]
            items = (self._area_items if self._area_items is not None
                     else list(self.dragged[area]))
            # 실측: 영역 li 사이에 uni_nm 없는 자리표시자(None)가 섞여 있다
            return [x for item in items for x in (item, None)]
        if selector.startswith("#colAdHocList1"):
            return list(self.dragged[selector.split(" ")[0]])
        if selector == layout.DESC_CELLS:
            if self._desc_cells is not None:
                return self._desc_cells
            return list(self.dragged[self.row_area])
        raise AssertionError(f"예상 못 한 셀렉터: {selector}")

    class _Mouse:
        def __init__(self, page):
            self._page = page

        def click(self, x, y):
            self._page.calls.append(("requery", x, y))

    @property
    def mouse(self):
        return _FakePage._Mouse(self)


def test_clears_both_areas_then_drags_then_requeries():
    page = _FakePage()
    layout.set_layout(page, rows=["(근무지역)시군구", "직종_중분류"])
    kinds = [c[0] for c in page.calls]
    assert kinds.index("click") < kinds.index("drag") < kinds.index("requery")
    assert ("click", page.row_clear) in page.calls
    assert ("click", page.col_clear) in page.calls


def test_fields_are_dragged_in_the_requested_outer_to_inner_order():
    """rows 는 '바깥→안쪽' 축 순서다. 실측(2026-09-03): 영역 **상단**에 떨어뜨리면
    드래그한 순서 그대로 쌓이므로 요청 순서 그대로 끌어놓는다.

    2026-09-02 실측은 영역 **중앙**에 떨어뜨려 "나중에 드래그한 것이 바깥"으로
    보였는데, 그것은 축이 둘일 때만 맞는 우연이었다(항목이 하나뿐인 영역의
    중앙은 그 항목 앞이라 앞에 끼어든다). 축이 셋인 경력직이동에서 그 규칙이
    깨졌다 — 요청 [시도, 산업, 산업(이전)] 이 [산업, 시도, 산업(이전)] 이 됐다."""
    page = _FakePage()
    layout.set_layout(page, rows=["(근무지역)시군구", "직종_중분류"])
    dragged = [_field_of(c[1]) for c in page.calls if c[0] == "drag"]
    assert dragged == ["(근무지역)시군구", "직종_중분류"]


def test_missing_field_raises_before_requery():
    """필드를 못 찾으면 조용히 넘어가지 않는다 — 재조회도 하지 않는다."""
    selector = layout.FIELD_TEMPLATE.format(field="직종_중분류")
    page = _FakePage(field_counts={selector: 0})
    with pytest.raises(layout.LayoutError):
        layout.set_layout(page, rows=["(근무지역)시군구", "직종_중분류"])
    assert not [c for c in page.calls if c[0] == "requery"]


def test_field_that_did_not_land_in_the_row_area_raises():
    """드래그가 먹지 않아 행 영역이 요청과 다르면 예외 — 조용히 다른 축을 수집하지 않는다."""
    page = _FakePage(area_items=["직종_중분류"])
    with pytest.raises(layout.LayoutError):
        layout.set_layout(page, rows=["(근무지역)시군구", "직종_중분류"])


def test_rendered_grid_axis_must_match_the_request():
    """재조회가 실제로 반영됐는지 렌더된 그리드의 행 축 설명 셀로 확인한다."""
    page = _FakePage(desc_cells=["(지역별)시도"])
    with pytest.raises(layout.LayoutError):
        layout.set_layout(page, rows=["(근무지역)시군구", "직종_중분류"])


def test_unexpected_viewport_width_raises():
    """재조회 버튼은 좌표 클릭이라 뷰포트 폭이 실측값과 다르면 엉뚱한 곳을 누른다."""
    page = _FakePage(viewport_width=800)
    with pytest.raises(layout.LayoutError):
        layout.set_layout(page, rows=["(지역별)시도"])


def test_hidden_spinner_node_does_not_count_as_busy():
    """실측(2026-09-02): '작업 취소' 노드는 항상 DOM 에 있고 숨김으로만 토글된다.
    존재만 보면(옛 probe 방식) 재조회가 끝나도 영원히 '진행 중'으로 보인다."""
    page = _FakePage(busy_forever=False)
    assert page.locator(f"text={layout.BUSY_TEXT}").count() == 1
    layout.set_layout(page, rows=["(지역별)시도"])       # 예외 없이 끝나야 한다


def test_busy_spinner_that_never_clears_raises():
    page = _FakePage(busy_forever=True)
    with pytest.raises(layout.LayoutError):
        layout.set_layout(page, rows=["(지역별)시도"])


def test_single_field_layout_succeeds():
    page = _FakePage()
    layout.set_layout(page, rows=["(지역별)시도"])
    assert ("requery",) + layout.SEARCH_BUTTON_XY in page.calls


def test_column_fields_are_placed_too():
    """마감년월을 열 축에 두는 기본 레이아웃도 만들 수 있어야 한다."""
    page = _FakePage()
    layout.set_layout(page, rows=["(지역별)시도"], cols=["마감년월"])
    assert page.dragged[page.col_area] == ["마감년월"]


def test_instance_id_is_read_from_the_page_not_hardcoded():
    """WISE 인스턴스 접미사는 **리포트마다 다르다** (2026-09-03 실측:
    유효구인구직 `_5990`, 취업건수 `_5987`, 피보험자 `_6248`). 상수로 박아 두면
    유효구인구직 말고는 초기화 클릭이 Playwright 타임아웃으로 죽는다 —
    첫 실측 수집이 정확히 그렇게 실패했다. 그래서 그 번호는 페이지에게 묻는다."""
    page = _FakePage(instance="_6248")
    layout.set_layout(page, rows=["(사업장)시도"], cols=["마감년월"])
    assert ("click", "#rowAdHocList1_6248_clear") in page.calls
    assert ("click", "#colAdHocList1_6248_clear") in page.calls
    assert page.dragged["#colAdHocList1_6248"] == ["마감년월"]


def test_missing_field_chooser_raises_instead_of_guessing_an_instance():
    """필드초이서를 못 찾으면 어림수를 쓰지 않고 시끄럽게 실패한다."""
    page = _FakePage()
    page.instance_ids = []
    with pytest.raises(layout.LayoutError):
        layout.set_layout(page, rows=["(지역별)시도"])


def test_three_row_fields_land_in_the_requested_order():
    """경력직이동은 행 축이 셋이다 — 2축에서 통한 규칙이 여기서 깨졌다.

    실측(2026-09-03) 요청 ['(사업장)시도', '산업_대분류', '산업(이전)_대분류'] 에
    대해 중앙 드롭+역순은 ['산업_대분류', '(사업장)시도', '산업(이전)_대분류'] 를
    만들었고, 상단 드롭+정순이 요청 그대로를 만들었다."""
    page = _FakePage(instance="_6157")
    rows = ["(사업장)시도", "산업_대분류", "산업(이전)_대분류"]
    layout.set_layout(page, rows=rows, cols=["마감년월"])
    assert page.dragged["#rowAdHocList1_6157"] == rows


def test_a_drag_that_does_not_register_is_retried_before_failing():
    """실측(2026-09-03, 피보험자): 드래그가 이따금 아예 안 먹는다.

    세 번째 실측 수집이 그렇게 죽었다 — 요청 ['(사업장)시군구', '직종_중분류'] 에
    실제로는 시군구 하나만 들어갔다. 그 자리까지 34분을 걸어온 수집이 통째로
    버려진다. 창 넘김(R61)·번호 클릭과 같은 이유이므로 같은 보호를 준다:
    다시 놓아 보고, 그래도 안 되면 그때 실패한다.
    """
    page = _FakePage(drops_to_ignore={"직종_중분류": 1})
    layout.set_layout(page, rows=["(사업장)시군구", "직종_중분류"])
    assert page.dragged[page.row_area] == ["(사업장)시군구", "직종_중분류"]


def test_a_drag_that_never_registers_still_raises():
    """재시도해도 안 들어가면 조용히 다른 축을 수집하지 않는다 — 예외는 그대로."""
    page = _FakePage(drops_to_ignore={"직종_중분류": 99})
    with pytest.raises(layout.LayoutError):
        layout.set_layout(page, rows=["(사업장)시군구", "직종_중분류"])
    assert not [c for c in page.calls if c[0] == "requery"]
