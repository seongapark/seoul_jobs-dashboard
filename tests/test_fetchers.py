"""pipeline.fetchers 테스트 — 네트워크 없이.

가짜 `get`(뷰어 주소 해석)과 가짜 그리드 수집기(`fetch`)를 주입한다. 브라우저도
Playwright 도 뜨지 않는다.
"""
import pytest

from pipeline import fetchers, layout
from pipeline.collect import Fetched

MENU_URL = ("https://eis.work24.go.kr/olap/report/viewer.do?USER=abc%3D%3D"
            "&assign_name=bWVpcw%3D%3D&dataScroll=Y&reportId=xyz%3D%3D&closYm=202601")


class _FakeResponse:
    def __init__(self, text):
        self.text = text


def _fake_get(url_template=MENU_URL):
    def get(url, **kwargs):
        return _FakeResponse(f'<input type="hidden" id="reptIdUrl" value="{url_template}">')
    return get


# ---------------------------------------------------------------------------
# 가짜 그리드 — 실측(2026-09-02) 그리드 모양을 그대로 본뜬다:
#   - 측정값 컬럼에 마감년월 접두가 붙는다 ("2026년 07월_유효구인인원(전체)")
#   - 행 축 칸이 레벨마다 따로 있다 (olap._EXTRACT_JS 가 rowspan 을 펴 준다)
#   - 시군구 축에는 수도권 밖 시군구, 시도 잔여 멤버("서울특별시"), "지역무관",
#     그룹 소계("… 전체") 가 함께 들어 있다
# ---------------------------------------------------------------------------

def _vacancy_grid(period="202607", gu=("6", "3"), seekers=("95", "80")):
    label = f"{period[:4]}년 {period[4:]}월"

    def row(sigungu, occupation, v, s):
        return {"(근무지역)시군구": sigungu, "직종_중분류": occupation,
                f"{label}_유효구인인원(전체)": v, f"{label}_유효구직자수(전체)": s}

    rows = [
        row("서울특별시 종로구", "2025직종_경영·행정·사무직", gu[0], seekers[0]),
        row("서울특별시 중구", "2025직종_경영·행정·사무직", gu[1], seekers[1]),
        row("부산광역시 중구", "2025직종_경영·행정·사무직", "9", "9"),   # 수도권 밖
        row("서울특별시", "2025직종_경영·행정·사무직", "0", "500"),        # 시도 잔여 멤버
        row("지역무관", "2025직종_경영·행정·사무직", "0", "300"),          # 지역 미지정
        row("2025직종_경영·행정·사무직 전체", "2025직종_경영·행정·사무직 전체", "1", "1"),
    ]
    summaries = [row("총계", "총계", "165,821", "1,550,154")]
    return rows, summaries


class _FakeGrid:
    """olap.fetch_and_parse_grid 를 대신한다 — 호출을 기록하고 after_load 를 실행한다."""

    def __init__(self, result=None, per_url=None, raises=None):
        self.calls = []
        self._result = result
        self._per_url = per_url or {}
        self._raises = raises or {}

    def __call__(self, url, *, browser, after_load=None, **kwargs):
        self.calls.append(url)
        if after_load is not None:
            after_load(object())          # set_layout 이 몽키패치돼 있다
        for needle, error in self._raises.items():
            if needle in url:
                raise error
        for needle, result in self._per_url.items():
            if needle in url:
                return result
        return self._result


@pytest.fixture
def recorded_layout(monkeypatch):
    """layout.set_layout 을 기록기로 바꾼다 — 어떤 축을 요청했는지 본다."""
    seen = []

    def record(page, *, rows, cols=()):
        seen.append({"rows": list(rows), "cols": list(cols)})

    monkeypatch.setattr(layout, "set_layout", record)
    return seen


class _CM:
    def center_of(self, code):
        return "서울강남고용센터"


# ---------------------------------------------------------------------------
# 1. month_url
# ---------------------------------------------------------------------------

def test_month_url_replaces_an_existing_clos_ym():
    url = fetchers.month_url("020010020", "202607", get=_fake_get())
    assert "closYm=202607" in url
    assert "closYm=202601" not in url


def test_month_url_appends_clos_ym_when_absent():
    bare = "https://eis.work24.go.kr/olap/report/viewer.do?USER=abc&reportId=xyz"
    url = fetchers.month_url("020010020", "202607", get=_fake_get(bare))
    assert url.endswith("closYm=202607")
    assert url.count("closYm=") == 1


def test_month_url_rejects_a_bad_period():
    with pytest.raises(ValueError):
        fetchers.month_url("020010020", "2026-07", get=_fake_get())


# ---------------------------------------------------------------------------
# 2. MONTHLY — 축과 파서
# ---------------------------------------------------------------------------

def test_vacancy_requests_the_sigungu_by_occupation_axis(recorded_layout):
    rows, summaries = _vacancy_grid()
    grid = _FakeGrid(result=fetchers.ParsedGridLike(rows, summaries))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)
    built["vacancy"]("202607")
    assert recorded_layout[0]["rows"] == ["(근무지역)시군구", "직종_중분류"]
    assert recorded_layout[0]["cols"] == ["마감년월"]


def test_vacancy_industry_requests_the_industry_axis(recorded_layout):
    rows, summaries = _vacancy_grid()
    for row in rows:
        row["산업_대분류"] = row.pop("직종_중분류")
    for row in summaries:
        row["산업_대분류"] = row.pop("직종_중분류")
    grid = _FakeGrid(result=fetchers.ParsedGridLike(rows, summaries))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)
    built["vacancy_industry"]("202607")
    assert recorded_layout[0]["rows"] == ["(근무지역)시군구", "산업_대분류"]


def test_every_screen_dataset_has_a_fetcher():
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(),
                                      fetch=_FakeGrid())
    assert set(built) == {"vacancy", "vacancy_industry", "vacancy_sido",
                          "placement", "placement_sido",
                          "insured", "insured_industry", "insured_sido", "mobility"}


def test_vacancy_rows_are_parsed_and_limited_to_the_metro_area(recorded_layout):
    rows, summaries = _vacancy_grid()
    grid = _FakeGrid(result=fetchers.ParsedGridLike(rows, summaries))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)
    fetched = built["vacancy"]("202607")
    assert isinstance(fetched, Fetched)
    assert [r["sigungu"] for r in fetched.rows] == ["11110", "11140"]
    assert fetched.rows[0]["period"] == "202607"
    assert fetched.rows[0]["vacancy"] == 6
    assert fetched.rows[0]["seekers"] == 95
    assert fetched.rows[0]["occupation"] == "경영·행정·사무직"


def test_period_that_does_not_match_the_requested_month_is_rejected(recorded_layout):
    """closYm 이 안 먹었는데 조용히 지난달 값을 쓰면 시계열이 통째로 거짓이 된다."""
    rows, summaries = _vacancy_grid(period="202606")
    grid = _FakeGrid(result=fetchers.ParsedGridLike(rows, summaries))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)
    with pytest.raises(fetchers.FetchError):
        built["vacancy"]("202607")


# ---------------------------------------------------------------------------
# 3. totals
# ---------------------------------------------------------------------------

def test_totals_come_from_the_summary_row(recorded_layout):
    rows, summaries = _vacancy_grid()
    grid = _FakeGrid(result=fetchers.ParsedGridLike(rows, summaries))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)
    fetched = built["vacancy"]("202607")
    assert fetched.totals == {"vacancy": 165821, "seekers": 1550154}


def test_totals_are_none_when_the_grid_gave_no_summary_row(recorded_layout):
    """지어내지 않는다 — run_monthly 가 그 자체를 실패로 보게 둔다(R18)."""
    rows, _ = _vacancy_grid()
    grid = _FakeGrid(result=fetchers.ParsedGridLike(rows, []))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)
    assert built["vacancy"]("202607").totals is None


# ---------------------------------------------------------------------------
# 4~6. SERIES — 달마다 한 번, 실패한 달은 건너뛰되 절반을 넘으면 예외
# ---------------------------------------------------------------------------

def _series_grid(period):
    label = f"{period[:4]}년 {period[4:]}월"
    rows = [{"(지역별)시도": name,
             f"{label}_유효구인인원(전체)": "10",
             f"{label}_유효구직자수(전체)": "100"}
            for name in ("서울", "경기", "인천", "부산")]
    return fetchers.ParsedGridLike(rows, [])


def test_series_fetches_once_per_month_and_merges(recorded_layout):
    periods = ["202605", "202606", "202607"]
    grid = _FakeGrid(per_url={p: _series_grid(p) for p in periods})
    built = fetchers.series_fetchers(periods, browser=object(), get=_fake_get(),
                                     fetch=grid, sleep=lambda s: None)
    rows = built["vacancy_series"]()
    assert len(grid.calls) == 3
    assert {r["period"] for r in rows} == set(periods)
    assert {r["sido"] for r in rows} == {"11", "41", "28"}


def test_series_skips_a_failing_month_and_keeps_the_rest(recorded_layout):
    periods = ["202605", "202606", "202607"]
    grid = _FakeGrid(per_url={p: _series_grid(p) for p in periods},
                     raises={"closYm=202606": RuntimeError("그리드 추출 실패 (가짜)")})
    skipped = []
    built = fetchers.series_fetchers(periods, browser=object(), get=_fake_get(),
                                     fetch=grid, sleep=lambda s: None,
                                     log=skipped.append)
    rows = built["vacancy_series"]()
    assert {r["period"] for r in rows} == {"202605", "202607"}
    assert any("202606" in line for line in skipped)


def test_series_raises_when_more_than_half_the_months_fail(recorded_layout):
    periods = ["202605", "202606", "202607", "202608"]
    grid = _FakeGrid(per_url={p: _series_grid(p) for p in periods},
                     raises={"closYm=20260": RuntimeError("전부 실패 (가짜)")})
    built = fetchers.series_fetchers(periods, browser=object(), get=_fake_get(),
                                     fetch=grid, sleep=lambda s: None)
    with pytest.raises(fetchers.SeriesBackfillError):
        built["vacancy_series"]()


def test_series_pauses_between_months(recorded_layout):
    periods = ["202605", "202606"]
    grid = _FakeGrid(per_url={p: _series_grid(p) for p in periods})
    slept = []
    built = fetchers.series_fetchers(periods, browser=object(), get=_fake_get(),
                                     fetch=grid, sleep=slept.append)
    built["vacancy_series"]()
    assert slept and all(s > 0 for s in slept)


def test_series_keys_match_the_screen_file_names():
    built = fetchers.series_fetchers(["202607"], browser=object(), get=_fake_get(),
                                     fetch=_FakeGrid(), sleep=lambda s: None)
    assert set(built) == {"vacancy_series", "insured_series"}
