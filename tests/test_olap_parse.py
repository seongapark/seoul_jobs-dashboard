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
    """page.locator(...).first.evaluate(...) / .count() 체인만 흉내낸다."""

    def __init__(self, page: "_FakePage"):
        self._page = page

    @property
    def first(self):
        return self

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
    """

    def __init__(self, windows=None, infinite_new_rows: bool = False,
                 header=None, scroller_raises: bool = False, pager_count: int = 1):
        self._windows = windows or []
        self._infinite = infinite_new_rows
        self._header = header or ["지역", "값"]
        self.scroller_raises = scroller_raises
        self.pager_count = pager_count
        self._call = 0
        self.scroll_calls = 0

    # Playwright page 인터페이스 중 fetch_grid 가 실제로 쓰는 것만 흉내낸다
    def goto(self, *a, **k):
        pass

    def wait_for_selector(self, *a, **k):
        pass

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


def test_fetch_grid_raises_when_grid_is_paginated_not_scrolled():
    """Task 7 Step 0 탐침(2026-09-01, tools/probe_flat_sigungu.py): (근무지역)시군구
    처럼 행이 많은 필드를 행 축에 놓으면 EIS 뷰어는 무한 스크롤이 아니라
    `.dx-datagrid-pager` 페이저로 나눠 보여준다 (실측: (지역별)시군구 단독
    ~250행 → 페이지 6개). 스크롤 누적은 같은 페이지 안에서만 맴돌다 "더 안
    늘어난다"며 안정화된 것으로 착각해 첫 페이지만 반환한다 — 그래서 스크롤을
    시도하기도 전에 페이저 존재를 확인해 시끄럽게 실패해야 한다."""
    page = _FakePage(windows=[[["a", "1"]]], pager_count=6)

    with pytest.raises(olap.OlapPaginationError) as exc_info:
        olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    msg = str(exc_info.value)
    assert "6" in msg
    assert page.scroll_calls == 0  # 스크롤을 시도하기도 전에 실패해야 한다


def test_fetch_grid_does_not_raise_pagination_error_for_single_page_grid():
    """페이저가 있어도(.dx-page 요소 1개 = 페이지 1개뿐) 정상 동작해야 한다 —
    OlapPaginationError 는 page 가 2개 이상일 때만."""
    windows = [[["a", "1"], ["b", "2"]], [["a", "1"], ["b", "2"]]]
    page = _FakePage(windows=windows, pager_count=1)

    rows = olap.fetch_grid("http://fake", page=page, max_scrolls=10)

    header, *body = rows
    assert {r[0] for r in body} == {"a", "b"}
