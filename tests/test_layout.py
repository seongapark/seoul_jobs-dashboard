"""pipeline.layout 테스트 — 가짜 page 스텁으로 드래그 조작 순서와 실패를 검증한다.
네트워크·브라우저 없음 (tests/test_olap_parse.py 의 스텁 스타일을 따른다)."""
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

    def drag_to(self, target):
        self._page.calls.append(("drag", self._selector, target._selector))
        self._page.dragged[target._selector].append(_field_of(self._selector))


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
                 viewport_width=layout.EXPECTED_VIEWPORT_WIDTH, busy_forever=False):
        self.calls = []
        self.dragged = {layout.ROW_AREA: [], layout.COL_AREA: []}
        self._area_items = area_items
        self._desc_cells = desc_cells
        self.field_counts = field_counts or {}
        self.viewport_size = {"width": viewport_width, "height": 720}
        self._busy_forever = busy_forever

    def click(self, selector):
        self.calls.append(("click", selector))

    def wait_for_timeout(self, ms):
        pass

    def locator(self, selector):
        if selector == f"text={layout.BUSY_TEXT}":
            return _BusyLocator(self._busy_forever)
        return _FakeLocator(self, selector)

    def eval_on_selector_all(self, selector, js):
        if selector.startswith(layout.ROW_AREA):
            items = (self._area_items if self._area_items is not None
                     else list(reversed(self.dragged[layout.ROW_AREA])))
            # 실측: 영역 li 사이에 uni_nm 없는 자리표시자(None)가 섞여 있다
            return [x for item in items for x in (item, None)]
        if selector.startswith(layout.COL_AREA):
            return list(reversed(self.dragged[layout.COL_AREA]))
        if selector == layout.DESC_CELLS:
            if self._desc_cells is not None:
                return self._desc_cells
            return list(reversed(self.dragged[layout.ROW_AREA]))
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
    assert ("click", layout.ROW_CLEAR) in page.calls
    assert ("click", layout.COL_CLEAR) in page.calls


def test_drag_order_puts_the_first_requested_field_outermost():
    """rows 는 '바깥→안쪽' 축 순서다. 실측(2026-09-02): 나중에 드래그한 필드가
    바깥쪽이 되므로 요청 순서의 역순으로 끌어놓아야 한다."""
    page = _FakePage()
    layout.set_layout(page, rows=["(근무지역)시군구", "직종_중분류"])
    dragged = [_field_of(c[1]) for c in page.calls if c[0] == "drag"]
    assert dragged == ["직종_중분류", "(근무지역)시군구"]


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
    assert page.dragged[layout.COL_AREA] == ["마감년월"]
