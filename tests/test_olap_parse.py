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
                 pager_wait_raises: bool = False, pager_labels=None,
                 grid_needs_requery: bool = False):
        self._windows = windows or []
        self._infinite = infinite_new_rows
        self._header = header or ["지역", "값"]
        self.scroller_raises = scroller_raises
        self.pager_count = pager_count
        self.pager_wait_raises = pager_wait_raises
        self.pager_labels = pager_labels
        self.pager_wait_calls = 0
        self._call = 0
        self.scroll_calls = 0
        self.click_calls = 0
        self.grid_needs_requery = grid_needs_requery
        self.after_load_done = False

    # Playwright page 인터페이스 중 fetch_grid 가 실제로 쓰는 것만 흉내낸다
    def goto(self, *a, **k):
        pass

    def wait_for_selector(self, selector, **k):
        if "pager" in selector:
            self.pager_wait_calls += 1
            if self.pager_wait_raises:
                raise TimeoutError(f"타임아웃 (가짜): {selector}")
            return
        if "pivotgrid-area-data" in selector and self.grid_needs_requery                 and not self.after_load_done:
            # 실측(2026-09-03, 경력직이동): 이 리포트는 조회를 누르기 전에는
            # 그리드가 아예 없다. 조회는 after_load(set_layout)가 한다.
            raise TimeoutError(f"타임아웃 (가짜): {selector}")
        # 그 외(예: area-data 컨테이너)는 항상 뜬 것으로 본다.

    def wait_for_timeout(self, *a, **k):
        pass

    def locator(self, selector):
        return _FakeLocator(self)

    def eval_on_selector_all(self, selector, js):
        """페이저 버튼의 라벨. 기본값은 '1'..'n' — 즉 전체 페이지가 다 보이는 상태.

        pager_labels 를 주면 그대로 돌려준다 (실측된 창 페이저 '…10 다음' 재현용).
        """
        if self.pager_labels is not None:
            return self.pager_labels
        return [str(i) for i in range(1, self.pager_count + 1)]

    def evaluate(self, js):
        if self._infinite:
            body = [[f"row{self._call}", str(self._call)]]
        else:
            idx = min(self._call, len(self._windows) - 1) if self._windows else 0
            body = self._windows[idx] if self._windows else []
        self._call += 1
        return [self._header, *body]

    def close(self):
        """browser.new_page() 로 열린 page 를 닫는 흉내 — fetch_and_parse_grid
        가 finally 에서 부른다. 아무것도 안 해도 된다."""


class _FakeBrowser:
    """`fetch_and_parse_grid(url, browser=...)` 가 쓰는 `browser.new_page()` 만
    흉내낸다 — 이미 만들어둔 `_FakePage` 하나를 그대로 돌려준다."""

    def __init__(self, page: "_FakePage"):
        self._page = page

    def new_page(self):
        return self._page


def test_fetch_grid_accumulates_across_windows_and_dedups_overlap():
    """가상화된 뷰포트가 매번 겹치는 창을 보여줘도 고유 행만 한 번씩 쌓인다."""
    windows = [
        [["a", "1"], ["b", "2"]],   # 최초 렌더 (스크롤 전)
        [["b", "2"], ["c", "3"]],   # 스크롤 1회 — b 는 겹침, c 는 새로 등장
        [["c", "3"], ["d", "4"]],   # 스크롤 2회 — c 는 겹침, d 는 새로 등장
        [["d", "4"]],               # 스크롤 3회 — 새 행 없음 → 안정화
    ]
    page = _FakePage(windows=windows)

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert grid.header == ["지역", "값"]
    assert {r[0] for r in grid.rows} == {"a", "b", "c", "d"}
    assert len(grid.rows) == 4  # 중복 없이 고유 행만


def test_fetch_grid_terminates_as_soon_as_a_window_adds_nothing_new():
    """새 행이 더 안 나오는 순간 멈춘다 — max_scrolls 를 다 돌지 않는다."""
    windows = [
        [["a", "1"]],
        [["a", "1"], ["b", "2"]],
        [["a", "1"], ["b", "2"]],  # 더 안 늘어남 → 여기서 멈춰야 한다
        [["a", "1"], ["b", "2"], ["c", "3"]],  # 이 창까지는 도달하면 안 된다
    ]
    page = _FakePage(windows=windows)

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert {r[0] for r in grid.rows} == {"a", "b"}
    assert "c" not in {r[0] for r in grid.rows}
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
    # R47 이후로는 총 페이지 수를 미리 알 수 없다(페이저는 창일 뿐이다) — 메시지가
    # 짚어야 하는 것은 "몇 페이지짜리인가"가 아니라 "어느 페이지에서 막혔는가"다.
    assert "2페이지" in msg
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

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert grid.header == ["지역", "값"]
    assert len(grid.rows) == 123
    assert [r[0] for r in grid.rows] == [f"row{i}" for i in range(123)]
    assert grid.summaries == []
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


def test_fetch_grid_raises_when_a_page_contributes_no_new_rows_even_if_reordered():
    """이전 페이지와 완전히 똑같은 리스트는 아니어도(순서만 다름) 새 행을
    하나도 못 보태면 "안 넘어간 것"과 똑같이 취급해 실패해야 한다 — 이전
    페이지와의 리스트 동등성(body == prev_body)만으로는 못 잡는 경우다."""
    page1 = [["a", "1"], ["b", "2"]]
    page2 = [["b", "2"], ["a", "1"]]  # 순서만 바뀜 — body != prev_body 지만 새 행 0개
    page = _FakePage(windows=[page1, page2], pager_count=2)

    with pytest.raises(olap.OlapPaginationError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert "새 행을 하나도 보태지" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Task 7b Fix round 3 (컨트롤러 R13/R14, 2026-09-02) — 개수 기반 상한
# ("중복 <= pager_count-1")은 실측(총계 행이 매 페이지에 고정 반복)에서
# 우연히 통과했을 뿐 원리적 근거가 없었다. 정체성 기반 규칙("중복된 행의
# 첫 칸이 알려진 요약 라벨인가")으로 교체했다.
# ---------------------------------------------------------------------------

def test_fetch_grid_raises_when_a_duplicated_row_is_not_a_known_summary_label():
    """R14: 페이지를 넘나들며 반복된 행이 있는데(예: 시군구 데이터 행 '강남구'가
    1·2페이지에 그대로 다시 나타남) 그 첫 칸이 알려진 요약 라벨이 아니면,
    옛 개수 기반 상한(중복 1개 <= 경계 2개)이었다면 조용히 통과시켰을
    상황이다 — 새 규칙은 개수가 아니라 정체성을 보므로, 이 데이터 행 중복을
    놓치지 않고 그 행을 이름 붙여 예외를 낸다."""
    dup_row = ["강남구", "1", "2"]
    page1 = [dup_row] + [[f"row{i}", str(i)] for i in range(49)]
    page2 = [dup_row] + [[f"row{i}", str(i)] for i in range(49, 98)]
    page3 = [[f"row{i}", str(i)] for i in range(98, 120)]
    page = _FakePage(windows=[page1, page2, page3], pager_count=3)

    with pytest.raises(olap.OlapPageWalkError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    msg = str(exc_info.value)
    assert "강남구" in msg
    assert "[1, 2]" in msg or ("1" in msg and "2" in msg)  # 등장 페이지


def test_fetch_grid_raises_when_a_duplicated_row_has_an_unknown_label():
    """R14: 반복된 행의 첫 칸이 '???' 처럼 전혀 모르는 라벨이면(총계/소계/합계/
    전체 어디에도 없음) 역시 개수와 무관하게 예외를 낸다 — 요약 라벨 목록은
    화이트리스트이지, 모르면 통과시키는 블랙리스트가 아니다."""
    dup_row = ["???", "1", "2"]
    page1 = [dup_row] + [[f"row{i}", str(i)] for i in range(49)]
    page2 = [dup_row] + [[f"row{i}", str(i)] for i in range(49, 98)]
    page = _FakePage(windows=[page1, page2], pager_count=2)

    with pytest.raises(olap.OlapPageWalkError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert "???" in str(exc_info.value)


def test_fetch_grid_does_not_raise_when_a_summary_row_repeats_more_than_page_boundaries_allow():
    """R14/R16: 총계 행이 페이지마다 두 번씩(예: 상단 고정 반복 + 우연한
    재렌더 — 실측으로 확인된 정상 패턴의 과장) 등장하면 3페이지에 걸쳐 총
    6번, 중복 5개다. 옛 개수 기반 상한(pager_count-1=2)이었다면 한참 초과해
    실패했을 상황이지만, 새 규칙은 개수가 아니라 정체성(알려진 요약 라벨인가)
    만 보므로 실패하지 않는다 — 옛 상한이 실제로 사라졌다는 증거다.
    (R16: 소계/합계/전체는 미확인이라 라벨 목록에서 뺐으므로, 이 테스트는
    실측으로 확인된 "총계" 하나만으로 같은 요점을 보인다.)"""
    total_row = ["총계", "100", "200"]
    page1 = [total_row, total_row] + [[f"row{i}", str(i)] for i in range(48)]
    page2 = [total_row, total_row] + [[f"row{i}", str(i)] for i in range(48, 96)]
    page3 = [total_row, total_row] + [[f"row{i}", str(i)] for i in range(96, 119)]
    page = _FakePage(windows=[page1, page2, page3], pager_count=3)

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert total_row not in grid.rows
    assert len(grid.rows) == 119  # 고유 데이터 행만 (요약 행은 본문에서 빠진다)
    assert grid.summaries == [total_row]  # 총계는 한 번만, 별도로


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

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert {r[0] for r in grid.rows} == {"a", "b"}


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

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert len(grid.rows) == 37


# ---------------------------------------------------------------------------
# Task 7b 후속 확인 (2026-09-02, tools/probe_pagination_dedup_evidence.py) —
# 262 vs 267 (5개 중복)의 실제 원인을 리터럴 행 텍스트로 확인했다: 5개 모두
# 서로 다른 행이 아니라 **같은 한 행**(총계) 이 6페이지 전부(1페이지 포함)에
# 다시 그려진 것이었다. "그룹이 페이지 경계에 걸쳐 헤더가 겹친다"는 원래
# 가설과는 메커니즘이 다르다(경계뿐 아니라 첫 페이지에도 나타났다) — 그래도
# 시군구 데이터 행이 아니라 grand-total 핀 행이므로 중복 제거가 맞다는
# 결론은 같다. 실측 텍스트 그대로 고정한다(합성 placeholder 아님).
# ---------------------------------------------------------------------------

def test_fetch_grid_collapses_the_pinned_grand_total_row_observed_live():
    """실측(2026-09-02, (지역별)시군구 단독 배치, 페이저 6페이지, 원시 267/고유
    262)에서 확인한 유일한 중복 행은 ['총계', '165,821', '1,550,154'] 였고,
    이 행은 1페이지를 포함해 모든 페이지 맨 위에 동일하게 다시 그려졌다(경계
    행이 아니라 grand-total 핀 행). R13(Fix round 3): 시군구 데이터 행이
    아니므로 본문에 섞지 않고 완전히 빼서 `.summaries` 에 한 번만 담아
    돌려줘야 한다(데이터 계약 — 총계는 분해값을 더해 만들지 않고 총계 행에서
    받는다) — 이 실제 텍스트로 그 판단을 고정한다."""
    total_row = ["총계", "165,821", "1,550,154"]
    page1 = [total_row] + [[f"region{i}", str(i)] for i in range(49)]
    page2 = [total_row] + [[f"region{i}", str(i)] for i in range(49, 98)]
    page3 = [total_row] + [[f"region{i}", str(i)] for i in range(98, 114)]  # 실측처럼 마지막 페이지 17행
    page = _FakePage(
        windows=[page1, page2, page3],
        pager_count=3,
        header=["(지역별)시군구", "유효구인인원(전체)", "유효구직자수(전체)"],
    )

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert grid.header == ["(지역별)시군구", "유효구인인원(전체)", "유효구직자수(전체)"]
    assert total_row not in grid.rows  # 본문에는 총계가 섞이지 않는다 (R13)
    assert len(grid.rows) == 114  # 114개 고유 지역만
    assert grid.summaries == [total_row]  # 총계는 한 번만, 별도로


# ---------------------------------------------------------------------------
# Task 7b Fix round 4 (컨트롤러 R15, 리뷰 루프) — fetch_and_parse_grid 는
# fetch_grid(Grid) 를 parse_grid 로 잇는 이음매다. R15 전에는 저장소 안에
# 부르는 곳도 테스트도 없었다 — Grid 로 이음매가 명시적이 된 지금, 총계 같은
# 요약 행이 이 이음매를 거쳐도 살아남는지(회귀 안 하는지) 가짜 page/browser 로
# 직접 확인한다. round trip 이 실제로 검증할 게 있다는 뜻이므로 삭제 대신 유지.
# ---------------------------------------------------------------------------

def test_fetch_and_parse_grid_round_trips_header_rows_and_summaries():
    """fetch_and_parse_grid 는 fetch_grid 의 Grid(header, rows, summaries) 를
    parse_grid 로 두 번(rows, summaries) 파싱해 ParsedGrid 로 돌려준다 — 총계
    행이 이 왕복을 거쳐도 조용히 사라지지 않아야 한다(R13/R15 가 지키려는
    데이터 계약을 실제 이음매에서 확인)."""
    total_row = ["총계", "165,821", "1,550,154"]
    page1 = [total_row] + [[f"region{i}", str(i)] for i in range(49)]
    page2 = [total_row] + [[f"region{i}", str(i)] for i in range(49, 98)]
    page = _FakePage(
        windows=[page1, page2],
        pager_count=2,
        header=["(지역별)시군구", "유효구인인원(전체)", "유효구직자수(전체)"],
    )
    browser = _FakeBrowser(page)

    result = olap.fetch_and_parse_grid("http://fake", browser=browser, max_scrolls=10)

    assert isinstance(result, olap.ParsedGrid)
    assert all(isinstance(d, dict) for d in result.rows)
    assert {d["(지역별)시군구"] for d in result.rows} == {f"region{i}" for i in range(98)}
    assert "총계" not in {d["(지역별)시군구"] for d in result.rows}
    assert len(result.summaries) == 1
    assert result.summaries[0] == {
        "(지역별)시군구": "총계",
        "유효구인인원(전체)": "165,821",
        "유효구직자수(전체)": "1,550,154",
    }


# ---------------------------------------------------------------------------
# R47 — 페이저 창 넘기기 (Task 15a 실측: 숫자 버튼은 최대 10개짜리 창이고
# 그 너머는 "다음" 버튼이다. 옛 코드는 `.dx-page` 개수를 전체 페이지 수로 믿어
# 예외 없이 잘린 그리드를 반환했다 — 실측에서 시군구 70개 중 14개만 수집됐다.)
# ---------------------------------------------------------------------------

_WINDOW = 10


class _FakePagedPage:
    """실측된 창 페이저를 충실히 흉내낸다.

    숫자 버튼은 현재 창(최대 10개)만 보이고, 뒤에 페이지가 더 있으면 끝에
    "다음" 이 붙는다. "다음" 은 창을 통째로 넘긴다. 숫자 클릭은 그 페이지로
    이동한다. (실제 EIS 의 "다음" 이 창을 넘기는지 한 칸만 넘기는지는 실측하지
    않았고, olap 은 번호로만 이동하므로 어느 쪽이든 결과가 같아야 한다 —
    그 성질을 _FakePagedNextAdvancesOnePage 가 따로 확인한다.)
    """

    def __init__(self, pages, header=None, extra_labels=(), render_delay_polls=0):
        self.pages = pages
        self._header = header or ["지역", "값"]
        self._extra_labels = list(extra_labels)
        self.current = 1
        self.window_start = 1
        self.scroll_calls = 0
        self.clicked = []
        # 실측: 무거운 그리드는 클릭 뒤 한참 이전 페이지를 그대로 보여준다.
        self._render_delay_polls = render_delay_polls
        self._displayed = 1
        self._pending = 0

    # --- 페이저 모델 -------------------------------------------------------
    def _labels(self):
        last = min(self.window_start + _WINDOW - 1, len(self.pages))
        labels = [str(n) for n in range(self.window_start, last + 1)]
        if last < len(self.pages):
            labels.append("다음")
        return labels + self._extra_labels

    def _click_index(self, index):
        label = self._labels()[index]
        self.clicked.append(label)
        if label.isdigit():
            self.current = int(label)
        elif label == "다음":
            self._advance_window()
        if self.current != self._displayed:
            self._pending = self._render_delay_polls

    def _advance_window(self):
        self.window_start = min(self.window_start + _WINDOW,
                                max(len(self.pages) - _WINDOW + 1, 1))

    # --- Playwright page 인터페이스 중 fetch_grid 가 쓰는 것만 ---------------
    def goto(self, *a, **k):
        pass

    def wait_for_selector(self, selector, **k):
        pass

    def wait_for_timeout(self, *a, **k):
        pass

    def close(self):
        pass

    def eval_on_selector_all(self, selector, js):
        return self._labels()

    def evaluate(self, js):
        if self._pending > 0:
            self._pending -= 1               # 아직 이전 페이지가 렌더돼 있다
        else:
            self._displayed = self.current
        return [self._header, *self.pages[self._displayed - 1]]

    def locator(self, selector):
        return _FakePagedLocator(self)


class _FakePagedNextAdvancesOnePage(_FakePagedPage):
    """"다음"이 창이 아니라 페이지를 한 칸 넘기는 변형.

    olap 이 번호로만 이동하므로 결과가 같아야 한다 — 그게 R47 종료 조건이
    "다음"의 의미에 기대지 않는다는 것의 증거다.
    """

    def _advance_window(self):
        self.current = min(self.current + 1, len(self.pages))
        if self.current > self.window_start + _WINDOW - 1:
            self.window_start += 1


class _FakePagedLocator:
    def __init__(self, page):
        self._page = page

    @property
    def first(self):
        return self

    def nth(self, index):
        self._index = index
        return self

    def click(self):
        self._page._click_index(self._index)

    def count(self):
        return len(self._page._labels())

    def evaluate(self, js):
        self._page.scroll_calls += 1


def _pages(count, header_row=None):
    """마지막 페이지만 짧은, 페이지당 50행짜리 가짜 그리드."""
    pages = []
    number = 0
    for index in range(count):
        size = olap._PAGE_SIZE if index < count - 1 else 17
        body = []
        for _ in range(size):
            body.append([f"region{number}", str(number)])
            number += 1
        pages.append(body)
    return pages


def test_fetch_grid_walks_past_the_ten_page_window():
    """R47 핵심 — 창(10개) 너머 페이지까지 전부 걷는다.

    옛 코드는 `.dx-page` 개수(=11, '다음' 포함)를 전체로 믿고 10페이지에서
    멈춰 잘린 그리드를 조용히 반환했다."""
    pages = _pages(23)
    page = _FakePagedPage(pages)

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    expected = {row[0] for body in pages for row in body}
    assert {row[0] for row in grid.rows} == expected
    assert len(grid.rows) == 22 * olap._PAGE_SIZE + 17
    assert page.clicked.count("다음") >= 2      # 창을 실제로 두 번 이상 넘겼다


def test_window_walk_does_not_depend_on_what_next_button_means():
    """'다음'이 창을 넘기든 페이지를 한 칸 넘기든 같은 결과여야 한다."""
    pages = _pages(23)
    page = _FakePagedNextAdvancesOnePage(pages)

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert {row[0] for row in grid.rows} == {row[0] for body in pages for row in body}


def test_walk_stops_when_no_higher_page_number_appears():
    """종료 조건 — 창에도, '다음'을 눌러 드러난 창에도 더 큰 번호가 없을 때 멈춘다."""
    pages = _pages(10)                     # 정확히 창 하나 = '다음' 버튼이 없다
    page = _FakePagedPage(pages)

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert len(grid.rows) == 9 * olap._PAGE_SIZE + 17
    assert "다음" not in page.clicked


def test_ten_pages_or_fewer_behave_exactly_as_before():
    """회귀 — 창 안에 다 들어가는 페이저는 예전 그대로 걷는다."""
    pages = _pages(6)
    page = _FakePagedPage(pages)

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert len(grid.rows) == 5 * olap._PAGE_SIZE + 17
    assert page.clicked == ["2", "3", "4", "5", "6"]


def test_unknown_pager_button_still_fails_loudly():
    """R47 가드는 유지된다 — 모르는 버튼이 생기면 걷지 않고 실패한다."""
    page = _FakePagedPage(_pages(12), extra_labels=["맨끝으로"])

    with pytest.raises(olap.OlapPaginationError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert "맨끝으로" in str(exc_info.value)


def test_walk_waits_for_the_grid_to_actually_rerender():
    """R47 실측(2026-09-02) — 무거운 그리드는 클릭 뒤 0.4초엔 이전 페이지가 그대로고
    3.4초쯤 갱신된다. 고정 대기 뒤에 읽으면 이전 페이지를 새 페이지로 착각해
    "행이 이전 페이지와 똑같다"로 죽는다(실제로 12페이지에서 그렇게 죽었다).
    본문이 바뀔 때까지 폴링해야 한다."""
    pages = _pages(14)
    page = _FakePagedPage(pages, render_delay_polls=6)

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert {row[0] for row in grid.rows} == {row[0] for body in pages for row in body}


def test_walk_still_fails_when_the_page_never_rerenders():
    """폴링 예산을 다 써도 안 바뀌면 예외 — 같은 페이지를 두 번 담지 않는다."""
    pages = _pages(12)
    page = _FakePagedPage(pages, render_delay_polls=olap._PAGE_RENDER_MAX_POLLS + 5)

    with pytest.raises(olap.OlapPageWalkError):
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)


def test_walk_that_cannot_advance_the_window_fails_instead_of_truncating():
    """R47 가드 — 창을 못 넘기면 조용히 잘린 결과를 내지 않는다.

    실측(2026-09-02): 창 넘김 뒤 라벨을 너무 일찍 읽으면 옛 창을 보고 "더 큰
    번호가 없다 = 끝"이라고 오판해 서울(25개 구)까지만 걷고 성공한 척했다.
    '다음' 이 아직 있는데 더 큰 번호가 안 나오면 그건 끝이 아니라 고장이다."""
    class _StuckWindow(_FakePagedPage):
        def _advance_window(self):
            pass                    # "다음"이 먹지 않는다

    page = _StuckWindow(_pages(14))

    with pytest.raises(olap.OlapPageWalkError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert "다음" in str(exc_info.value)


def test_a_last_page_that_is_exactly_full_is_not_a_failure():
    """실측 오탐 회귀 — 이 그리드는 정확히 200페이지 × 50행이라 **마지막 페이지가
    꽉 차 있었다**(마지막 행 '전북특별자치도 부안군'). 처음엔 "마지막 페이지는
    보통 덜 찬다"는 어림으로 완전성을 봤다가 멀쩡히 끝까지 걷고도 실패했다.
    끝인지 아닌지는 어림이 아니라 '다음' 버튼의 부재로 판단한다."""
    pages = [[[f"region{i * olap._PAGE_SIZE + j}", "1"] for j in range(olap._PAGE_SIZE)]
             for i in range(12)]                    # 12페이지 전부 꽉 참
    page = _FakePagedPage(pages)

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert len(grid.rows) == 12 * olap._PAGE_SIZE


def test_window_labels_that_arrive_late_are_waited_for():
    """라벨이 늦게 갱신돼도 창을 제대로 넘긴다 (본문 렌더 지연과 같은 이유)."""
    class _LateLabels(_FakePagedPage):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._lag = 0

        def _advance_window(self):
            super()._advance_window()
            self._lag = 5           # 다섯 번은 옛 창 라벨을 그대로 보여준다

        def _labels(self):
            labels = super()._labels()
            if self._lag > 0:
                self._lag -= 1
                start = max(self.window_start - _WINDOW, 1)
                last = min(start + _WINDOW - 1, len(self.pages))
                return [str(n) for n in range(start, last + 1)] + ["다음"]
            return labels

    pages = _pages(14)
    page = _LateLabels(pages)

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert {row[0] for row in grid.rows} == {row[0] for body in pages for row in body}


def test_a_click_that_does_not_take_is_retried_once():
    """실측(2026-09-02): 200페이지짜리 걷기에서 클릭 하나가 이따금 먹지 않는다
    (151페이지까지 잘 가다가 152페이지에서 렌더가 안 바뀌었다). 한 번은 다시
    눌러 보되, 그래도 안 바뀌면 여전히 예외다(위 테스트)."""
    pages = _pages(12)

    class _DropsOneClick(_FakePagedPage):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._dropped = False

        def _click_index(self, index):
            label = self._labels()[index]
            if label == "4" and not self._dropped:
                self._dropped = True
                self.clicked.append(label)
                return                      # 이 클릭은 먹지 않는다
            super()._click_index(index)

    page = _DropsOneClick(pages)

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    assert page._dropped
    assert {row[0] for row in grid.rows} == {row[0] for body in pages for row in body}


def test_fetch_grid_reads_reports_whose_grid_appears_only_after_the_requery():
    """실측(2026-09-03, 경력직이동): 이 리포트는 조회를 누르기 전에 그리드가 없다.

    그리드를 after_load **전에** 기다리면 60초를 다 쓰고 타임아웃으로 죽는다 —
    첫 실측 수집에서 mobility 가 정확히 그렇게 실패했다. 그리드는 축을 바꾸고
    조회한 **뒤에** 기다려야 한다.
    """
    page = _FakePage(windows=[[["서울", "10"]]], grid_needs_requery=True)

    def after_load(p):
        p.after_load_done = True

    grid = olap.fetch_grid("http://fake", page=page, max_scrolls=5, after_load=after_load)
    assert grid.rows == [["서울", "10"]]
