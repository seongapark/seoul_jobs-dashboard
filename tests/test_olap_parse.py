"""pipeline.olap 테스트 — parse_grid(순수 파서) + fetch_grid(가짜 page 로 스크롤-누적
로직만 검증, 네트워크/브라우저 없음)."""
import json
from pathlib import Path

import pytest

from pipeline import olap

FIXTURE = Path(__file__).parent / "fixtures/olap_grid.json"


def test_parse_grid_pairs_header_with_rows():
    rows = [["지역", "유효구인인원", "유효구직건수"],
            ["서울", "29,196", "268,616"],
            ["경기", "45,743", "407,355"]]
    parsed = olap.parse_grid(rows)
    assert parsed[0] == {"지역": "서울", "유효구인인원": "29,196", "유효구직건수": "268,616"}
    assert len(parsed) == 2


def test_parse_grid_against_live_fixture():
    """tools/_e2e_fetch.py 로 2026-09-01 실제 뷰어에서 한 번 받아 저장한 표본.
    docs 에 적힌 2026년 07월 검증값 네 개와 정확히 일치해야 한다."""
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parsed = olap.parse_grid(rows)
    by_region = {d["(지역별)시도"]: d for d in parsed}

    expected = {
        "총계": ("165,821", "1,550,154"),
        "서울": ("29,196", "268,616"),
        "경기": ("45,743", "407,355"),
        "인천": ("7,501", "99,637"),
    }
    gu_key = "2026년 07월_유효구인인원(전체)"
    gj_key = "2026년 07월_유효구직자수(전체)"
    for region, (gu, gj) in expected.items():
        assert by_region[region][gu_key] == gu
        assert by_region[region][gj_key] == gj

    # 헤더 1행 + 17개 시도(전남/광주 통합 표기 포함, 총계 포함) 행
    assert len(parsed) == 17


def test_parse_grid_row_count_matches_header_free_body():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    parsed = olap.parse_grid(rows)
    assert len(parsed) == len(rows) - 1


# ---------------------------------------------------------------------------
# fetch_grid — 가짜 page 로 스크롤-누적/가상화 로직 검증 (네트워크·브라우저 없음)
# ---------------------------------------------------------------------------

class _FakeLocator:
    """page.locator(...).first.evaluate(...) / .count() / .nth(i).click() 체인만 흉내낸다."""

    def __init__(self, page: "_FakePage"):
        self._page = page

    @property
    def first(self):
        return self

    def nth(self, index):
        return self

    def click(self):
        self._page.click_calls += 1

    def evaluate(self, js):
        self._page.scroll_calls += 1
        if self._page.scroller_raises:
            raise RuntimeError("스크롤 대상 없음 (가짜)")

    def count(self):
        return self._page.pager_count


class _FakePage:
    """dx-pivotgrid 가상화를 흉내낸다.

    windows: page.evaluate(_EXTRACT_JS) 를 부를 때마다 순서대로 반환할 "현재 보이는
    본문 행" 목록. 마지막 윈도우를 넘어서 호출되면 마지막 윈도우를 반복한다
    (= 더 스크롤해도 안 늘어남 = 안정화).
    infinite_new_rows=True 면 호출마다 이전에 없던 새 행을 계속 만들어낸다
    (= 가상화가 절대 끝나지 않는 고장 상황을 흉내낸다).

    pager_wait_raises: 페이저 컨테이너(_PAGER_CONTAINER_SELECTOR)를 명시적으로
    기다리는 wait_for_selector 호출이 타임아웃(=페이저가 안 떴다)나는지 여부.
    False(기본)면 "결국 떴다"고 보고 그냥 리턴한다 — 실제 Playwright 가 폴링
    끝에 찾아내는 것과 같은 결과다. area-data 컨테이너를 기다리는 첫 호출은
    항상 성공한 것으로 본다.
    """

    def __init__(self, windows=None, infinite_new_rows: bool = False,
                 header=None, scroller_raises: bool = False, pager_count: int = 1,
                 pager_wait_raises: bool = False):
        self._windows = windows or []
        self._infinite = infinite_new_rows
        self._header = header or ["지역", "값"]
        self.scroller_raises = scroller_raises
        self.pager_count = pager_count
        self.pager_wait_raises = pager_wait_raises
        self.pager_wait_calls = 0
        self._call = 0
        self.scroll_calls = 0
        self.click_calls = 0

    # Playwright page 인터페이스 중 fetch_grid 가 실제로 쓰는 것만 흉내낸다
    def goto(self, *a, **k):
        pass

    def wait_for_selector(self, selector, **k):
        if "pager" in selector:
            self.pager_wait_calls += 1
            if self.pager_wait_raises:
                raise TimeoutError(f"타임아웃 (가짜): {selector}")
        # 그 외(예: area-data 컨테이너)는 항상 뜬 것으로 본다.

    def wait_for_timeout(self, *a, **k):
        pass

    def locator(self, selector):
        return _FakeLocator(self)

    def evaluate(self, js):
        if self._infinite:
            body = [[f"row{self._call}", str(self._call)]]
        else:
            idx = min(self._call, len(self._windows) - 1) if self._windows else 0
            body = self._windows[idx] if self._windows else []
        self._call += 1
        return [self._header, *body]


def test_fetch_grid_accumulates_across_windows_and_dedups_overlap():
    """가상화된 뷰포트가 매번 겹치는 창을 보여줘도 고유 행만 한 번씩 쌓인다."""
    windows = [
        [["a", "1"], ["b", "2"]],   # 최초 렌더 (스크롤 전)
        [["b", "2"], ["c", "3"]],   # 스크롤 1회 — b 는 겹침, c 는 새로 등장
        [["c", "3"], ["d", "4"]],   # 스크롤 2회 — c 는 겹침, d 는 새로 등장
        [["d", "4"]],               # 스크롤 3회 — 새 행 없음 → 안정화
    ]
    page = _FakePage(windows=windows)

    rows = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    header, *body = rows
    assert header == ["지역", "값"]
    assert {r[0] for r in body} == {"a", "b", "c", "d"}
    assert len(body) == 4  # 중복 없이 고유 행만


def test_fetch_grid_terminates_as_soon_as_a_window_adds_nothing_new():
    """새 행이 더 안 나오는 순간 멈춘다 — max_scrolls 를 다 돌지 않는다."""
    windows = [
        [["a", "1"]],
        [["a", "1"], ["b", "2"]],
        [["a", "1"], ["b", "2"]],  # 더 안 늘어남 → 여기서 멈춰야 한다
        [["a", "1"], ["b", "2"], ["c", "3"]],  # 이 창까지는 도달하면 안 된다
    ]
    page = _FakePage(windows=windows)

    rows = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    header, *body = rows
    assert {r[0] for r in body} == {"a", "b"}
    assert "c" not in {r[0] for r in body}
    assert page.scroll_calls == 2  # windows[1] 까지 갔다가 windows[2] 에서 안 늘어 멈춤


def test_fetch_grid_raises_when_rows_never_stabilize():
    """가짜가 영원히 새 행을 뱉으면 (가상화가 안 끝나는 고장) max_scrolls 에서
    조용히 잘린 그리드를 반환하지 않고 이름 있는 예외를 낸다."""
    page = _FakePage(infinite_new_rows=True)

    with pytest.raises(olap.OlapExtractionError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=5)

    msg = str(exc_info.value)
    assert "5" in msg  # 캡 값이 메시지에 남아야 한다
    assert "행" in msg  # 수집된 행 수 언급


def test_fetch_grid_raises_when_grid_has_no_body_rows():
    """컨테이너는 렌더됐지만 데이터 행이 하나도 없으면 [header] 를 조용히
    반환하지 말고 예외를 낸다."""
    page = _FakePage(windows=[[]])  # 매번 빈 본문

    with pytest.raises(olap.OlapExtractionError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert "데이터 행" in str(exc_info.value)


def test_fetch_grid_raises_when_page_click_does_not_change_rendered_rows():
    """Task 7b: 페이저가 페이지 6개라는데 다음 페이지로 클릭해 이동해도 렌더된 행이
    이전 페이지와 그대로면(셀렉터가 안 맞거나 클릭이 안 먹은 경우) "더 안 늘어난다"며
    안정화된 것으로 착각해 첫 페이지만 반환하면 안 된다 — 스크롤 폴백으로 새지 않고
    시끄럽게 실패해야 한다."""
    page = _FakePage(windows=[[["a", "1"]]], pager_count=6)

    with pytest.raises(olap.OlapPaginationError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    msg = str(exc_info.value)
    assert "6" in msg
    assert page.scroll_calls == 0  # 스크롤 폴백으로 새지 않는다


# ---------------------------------------------------------------------------
# Task 7b — 페이지네이션 누적: 실제로 페이지 버튼을 눌러가며 전 페이지를 걷는다.
# ---------------------------------------------------------------------------

def test_fetch_grid_walks_all_pages_and_accumulates_in_order():
    """페이저가 3페이지라고 보고하면(50/50/23행), 스크롤 대신 페이지 버튼을
    순서대로 눌러가며 전량(123행)을 중복 없이, 페이지 순서 그대로 누적해야
    한다. 헤더는 한 번만 남는다."""
    page1 = [[f"row{i}", str(i)] for i in range(50)]
    page2 = [[f"row{i}", str(i)] for i in range(50, 100)]
    page3 = [[f"row{i}", str(i)] for i in range(100, 123)]
    page = _FakePage(windows=[page1, page2, page3], pager_count=3)

    rows = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    header, *body = rows
    assert header == ["지역", "값"]
    assert len(body) == 123
    assert [r[0] for r in body] == [f"row{i}" for i in range(123)]
    assert page.click_calls == 2  # 1페이지는 이미 로드됨 — 2, 3페이지로만 이동
    assert page.scroll_calls == 0  # 스크롤 폴백을 쓰지 않는다


def test_fetch_grid_raises_when_a_later_page_returns_zero_body_rows():
    """도중 한 페이지가 데이터 행을 하나도 안 돌려주면(렌더 실패 등) 조용히 나머지
    페이지만으로 그럴듯한 결과를 만들지 않고 예외를 낸다."""
    page1 = [[f"row{i}", str(i)] for i in range(50)]
    windows = [page1, []]  # 2페이지가 텅 빔
    page = _FakePage(windows=windows, pager_count=3)

    with pytest.raises(olap.OlapExtractionError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert "2페이지" in str(exc_info.value)


def test_fetch_grid_raises_when_accumulated_count_disagrees_with_pager_implied_total():
    """세 페이지 각각은 페이지 크기 규칙을 지키는데(50/50/23), 2페이지 첫 행이
    1페이지 행과 내용이 우연히 같아 중복 판정으로 사라진다 — 페이저가 암시하는
    총합(123)과 실제 누적 고유 행(122)이 어긋나므로 조용히 넘어가지 않고 예외를
    내야 한다."""
    page1 = [[f"row{i}", str(i)] for i in range(50)]
    page2 = [["row0", "0"]] + [[f"row{i}", str(i)] for i in range(50, 99)]
    page3 = [[f"row{i}", str(i)] for i in range(99, 122)]
    page = _FakePage(windows=[page1, page2, page3], pager_count=3)

    with pytest.raises(olap.OlapPaginationError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    msg = str(exc_info.value)
    assert "123" in msg
    assert "122" in msg


def test_fetch_grid_raises_when_a_non_last_page_is_short():
    """마지막 페이지가 아닌 페이지가 _PAGE_SIZE 보다 적은 행을 돌려주면(페이지가
    잘못 넘어갔을 가능성) 조용히 넘어가지 않고 예외를 낸다."""
    page1 = [[f"row{i}", str(i)] for i in range(50)]
    page2 = [[f"row{i}", str(i)] for i in range(50, 80)]  # 30행 — 마지막이 아닌데 부족
    page3 = [[f"row{i}", str(i)] for i in range(80, 103)]
    page = _FakePage(windows=[page1, page2, page3], pager_count=3)

    with pytest.raises(olap.OlapPaginationError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    msg = str(exc_info.value)
    assert "2페이지" in msg
    assert "30" in msg


def test_fetch_grid_does_not_raise_pagination_error_for_single_page_grid():
    """페이저가 있어도(.dx-page 요소 1개 = 페이지 1개뿐) 정상 동작해야 한다 —
    OlapPaginationError 는 page 가 2개 이상일 때만."""
    windows = [[["a", "1"], ["b", "2"]], [["a", "1"], ["b", "2"]]]
    page = _FakePage(windows=windows, pager_count=1)

    rows = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    header, *body = rows
    assert {r[0] for r in body} == {"a", "b"}


# ---------------------------------------------------------------------------
# 코디네이터 Fix round 1 — 페이저 탐지가 고정 500ms 대기 하나에만 기대지 않게
# 두 가지 독립된 방어를 더했다: (1) 페이저 컨테이너 자체를 명시적으로 기다리고,
# (2) 페이저가 안 잡혀도 본문 행 수가 페이지 크기의 정확한 배수면 탐지 실패로
# 본다(시간과 무관한 교차검증).
# ---------------------------------------------------------------------------

def test_fetch_grid_pager_detected_after_explicit_wait_not_a_fixed_sleep():
    """페이저가 area-data 컨테이너보다 늦게 뜨는 상황을 흉내낸다. 고정 시간
    대기 뒤 곧장 세는 방식이었다면 이 시나리오에서 늦게 뜬 페이저를 놓쳐
    "없다"고 오판했을 것이다 — 페이저 컨테이너를 명시적으로 기다려야
    (설령 그 사이 폴링이 있었더라도) 여전히 잡아내고 실패해야 한다."""
    page = _FakePage(windows=[[["a", "1"]]], pager_count=6, pager_wait_raises=False)

    with pytest.raises(olap.OlapPaginationError):
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert page.pager_wait_calls == 1  # 페이저 컨테이너를 실제로 기다렸다
    assert page.scroll_calls == 0  # 스크롤을 시도하기도 전에 실패했다


def test_fetch_grid_raises_when_body_is_exact_page_size_multiple_with_no_pager_detected():
    """페이저 셀렉터가 바뀌어 탐지 자체가 실패한 상황을 흉내낸다(대기해도 못
    찾음). 그런데 본문 행 수가 정확히 페이지 크기(_PAGE_SIZE)의 배수다 —
    데이터가 우연히 그 경계에서 끝났다고 보기보다 탐지 실패로 보고 역시
    시끄럽게 실패해야 한다."""
    body = [[f"row{i}", str(i)] for i in range(olap._PAGE_SIZE)]
    page = _FakePage(windows=[body], pager_count=1, pager_wait_raises=True)

    with pytest.raises(olap.OlapPaginationError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    msg = str(exc_info.value)
    assert str(olap._PAGE_SIZE) in msg
    assert page.scroll_calls == 0  # 교차검증은 스크롤 전에 걸린다


def test_fetch_grid_returns_normally_when_no_pager_and_row_count_is_not_a_page_boundary():
    """페이저를 못 찾았고, 본문 행 수(37)도 페이지 크기의 배수가 아니다 —
    진짜로 페이저가 없는 정상적인 작은 그리드다. 예외 없이 그대로 반환해야
    한다."""
    body = [[f"row{i}", str(i)] for i in range(37)]
    page = _FakePage(windows=[body], pager_count=1, pager_wait_raises=True)

    rows = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    header, *out_body = rows
    assert len(out_body) == 37
