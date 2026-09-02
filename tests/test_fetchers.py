"""pipeline.fetchers 테스트 — 네트워크 없이.

가짜 `get`(뷰어 주소 해석)과 가짜 그리드 수집기(`fetch`)를 주입한다. 브라우저도
Playwright 도 뜨지 않는다.
"""
import pytest

from pipeline import fetchers, layout, olap
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
    grid = _FakeGrid(result=olap.ParsedGrid(rows, summaries))
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
    grid = _FakeGrid(result=olap.ParsedGrid(rows, summaries))
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
    grid = _FakeGrid(result=olap.ParsedGrid(rows, summaries))
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
    grid = _FakeGrid(result=olap.ParsedGrid(rows, summaries))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)
    with pytest.raises(fetchers.FetchError):
        built["vacancy"]("202607")


# ---------------------------------------------------------------------------
# 3. totals
# ---------------------------------------------------------------------------

def test_totals_come_from_the_summary_row(recorded_layout):
    rows, summaries = _vacancy_grid()
    grid = _FakeGrid(result=olap.ParsedGrid(rows, summaries))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)
    fetched = built["vacancy"]("202607")
    assert fetched.totals == {"vacancy": 165821, "seekers": 1550154}


def test_totals_are_none_when_the_grid_gave_no_summary_row(recorded_layout):
    """지어내지 않는다 — run_monthly 가 그 자체를 실패로 보게 둔다(R18)."""
    rows, _ = _vacancy_grid()
    grid = _FakeGrid(result=olap.ParsedGrid(rows, []))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)
    assert built["vacancy"]("202607").totals is None


# ---------------------------------------------------------------------------
# 4~6. SERIES — 달마다 한 번, 실패한 달은 건너뛰되 절반을 넘으면 예외
# ---------------------------------------------------------------------------

def _series_grid(period):
    label = f"{period[:4]}년 {period[4:]}월"
    rows = [{"(근무지역)시도": name,
             f"{label}_유효구인인원(전체)": "10",
             f"{label}_유효구직자수(전체)": "100"}
            for name in ("서울", "경기", "인천", "부산")]
    return olap.ParsedGrid(rows, [])


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


# ---------------------------------------------------------------------------
# 리뷰 Critical 1 — 예외 없이 0행이 나오는 달도 실패로 센다.
#
# 그리드가 깨끗이 받아지고 파싱까지 됐는데 _metro_only 가 하나도 못 맞추면
# (시도 라벨이 '서울' -> '서울특별시' 로 바뀌기만 해도) 예외가 없다. 그 아래에는
# 그물이 없다 — run_series 에는 check_not_all_zero 의 짝이 없고
# check_series_shape([])/check_series_months([]) 는 둘 다 무사통과라, 빈
# 시계열 파일이 새 collected_at 과 함께 조용히 덮어써진다.
# ---------------------------------------------------------------------------

def _renamed_sido_grid(period):
    """EIS 가 시도 라벨 표기만 바꾼 상황 — 예외는 없고 필터가 전부 버린다."""
    label = f"{period[:4]}년 {period[4:]}월"
    rows = [{"(근무지역)시도": name,
             f"{label}_유효구인인원(전체)": "10",
             f"{label}_유효구직자수(전체)": "100"}
            for name in ("서울특별시", "경기도", "인천광역시")]
    return olap.ParsedGrid(rows, [])


def test_series_month_filtered_down_to_zero_rows_counts_as_failed(recorded_layout):
    """0행이 된 달은 '성공'이 아니다 — 실패로 세어 절반 규칙이 작동하게 한다."""
    periods = ["202605", "202606", "202607"]
    # 키는 URL 부분문자열이고 먼저 넣은 것이 이긴다 — 겹치지 않게 전부 closYm= 로 준다
    per_url = {f"closYm={p}": (_renamed_sido_grid(p) if p == "202606" else _series_grid(p))
               for p in periods}
    grid = _FakeGrid(per_url=per_url)
    logged = []
    built = fetchers.series_fetchers(periods, browser=object(), get=_fake_get(),
                                     fetch=grid, sleep=lambda s: None, log=logged.append)

    rows = built["vacancy_series"]()

    assert {r["period"] for r in rows} == {"202605", "202607"}
    assert any("202606" in line and "0행" in line for line in logged)


def test_series_raises_when_every_month_is_filtered_down_to_zero(recorded_layout):
    """라벨 표기가 바뀌어 전 기간이 0행이 되면 빈 파일을 덮어쓰지 않고 실패한다."""
    periods = ["202605", "202606", "202607"]
    grid = _FakeGrid(result=_renamed_sido_grid("202607"),
                     per_url={p: _renamed_sido_grid(p) for p in periods})
    built = fetchers.series_fetchers(periods, browser=object(), get=_fake_get(),
                                     fetch=grid, sleep=lambda s: None,
                                     log=lambda line: None)

    with pytest.raises(fetchers.SeriesBackfillError):
        built["vacancy_series"]()


def test_series_never_returns_an_empty_backfill(recorded_layout):
    """받을 달이 하나도 없어도 '성공'으로 빈 이력을 내려보내지 않는다."""
    built = fetchers.series_fetchers([], browser=object(), get=_fake_get(),
                                     fetch=_FakeGrid(), sleep=lambda s: None)
    with pytest.raises(fetchers.SeriesBackfillError):
        built["vacancy_series"]()


# ---------------------------------------------------------------------------
# 리뷰 Important 2 — 요청한 달을 지어내 도장찍지 않는다.
# ---------------------------------------------------------------------------

def test_rows_without_any_period_column_are_rejected(recorded_layout):
    """접두도 리터럴 마감년월도 없으면 실패한다 — 예전엔 요청한 달로 채워서,
    closYm 교차검증이 '헤더에 접두가 있을 때만' 도는 조건부가 됐다."""
    rows = [{"(근무지역)시도": "서울",
             "유효구인인원(전체)": "10", "유효구직자수(전체)": "100"}]
    grid = _FakeGrid(result=olap.ParsedGrid(rows, []))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)

    with pytest.raises(fetchers.FetchError):
        built["vacancy_sido"]("202607")


def test_a_literal_period_column_is_accepted(recorded_layout):
    """마감년월이 행 축에 있어 리터럴 컬럼으로 오는 경우는 그대로 받는다."""
    rows = [{"(근무지역)시도": "서울", "마감년월": "2026년 07월",
             "유효구인인원(전체)": "10", "유효구직자수(전체)": "100"}]
    grid = _FakeGrid(result=olap.ParsedGrid(rows, []))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)

    fetched = built["vacancy_sido"]("202607")
    assert fetched.rows[0]["period"] == "202607"


def test_collapsed_nested_header_cell_is_rejected(recorded_layout):
    """리뷰 Important 4 — 중첩 헤더 전개가 무너지면 축 칸이 '' 로 남는다.
    지역 축이 무너진 행은 _metro_only 가 버려 완전성 검사가 잡지만, 직종 축이
    무너진 행은 '' 인 채로 살아남는다 — 그건 여기서 잡아야 한다."""
    rows, summaries = _vacancy_grid()
    rows[0]["직종_중분류"] = ""            # 전개가 무너진 칸
    grid = _FakeGrid(result=olap.ParsedGrid(rows, summaries))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)

    with pytest.raises(fetchers.checks.CheckFailed):
        built["vacancy"]("202607")


# ---------------------------------------------------------------------------
# R53 — 경기 일반구를 버리지 말고 모시로 합산 이관한다.
#
# 실측(2026-09-02): 일반구 24개를 버리면 경기 유효구인인원의 45.5%
# (22,289/48,938)가 사라지고 수원·성남·고양·용인이 구인 0 으로 나온다.
# ---------------------------------------------------------------------------

def _gyeonggi_grid(period="202607"):
    label = f"{period[:4]}년 {period[4:]}월"

    def row(name, v, s):
        return {"(근무지역)시군구": name, "직종_중분류": "2025직종_경영·행정·사무직",
                f"{label}_유효구인인원(전체)": v, f"{label}_유효구직자수(전체)": s}

    rows = [
        row("경기도 수원시", "0", "19,521"),          # 시 레벨 잔여 — 구인이 0 이다
        row("경기도 수원시 장안구", "500", "1,000"),
        row("경기도 수원시 권선구", "300", "700"),
        row("경기도 이천시", "1,856", "4,396"),        # 일반구가 없는 시
        row("경기도", "0", "43,823"),                  # 시도 잔여 멤버
        row("경상남도 창원시 성산구", "9", "9"),        # 수도권 밖 일반구 — 그냥 버린다
    ]
    return olap.ParsedGrid(rows, [row("총계", "165,821", "1,550,154")])


def test_general_districts_are_merged_into_their_parent_city(recorded_layout):
    """수원시가 0 이 아니어야 한다 — 시 레벨 잔여 + 일반구 합."""
    grid = _FakeGrid(result=_gyeonggi_grid())
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)

    rows = built["vacancy"]("202607").rows
    by_code = {r["sigungu"]: r for r in rows}

    assert by_code["41110"]["vacancy"] == 800            # 0 + 500 + 300
    assert by_code["41110"]["seekers"] == 21221          # 19,521 + 1,000 + 700
    assert by_code["41500"]["vacancy"] == 1856           # 일반구 없는 시는 그대로
    assert "41111" not in by_code                        # 출력 축에 일반구는 없다


def test_metro_general_district_without_a_parent_raises(recorded_layout):
    """모시를 못 찾으면 조용히 버리지 않는다 — 그게 애초에 이 문제를 만든 실패 모양이다."""
    grid = _gyeonggi_grid()
    grid.rows.append({**grid.rows[1], "(근무지역)시군구": "경기도 없는시 어떤구"})
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(),
                                      fetch=_FakeGrid(result=grid))
    with pytest.raises(fetchers.FetchError):
        built["vacancy"]("202607")


def test_residual_is_collected_per_sido_for_the_sido_check(recorded_layout):
    """시도 잔여('경기도' 행)를 버리지 않고 시도별로 모아 넘긴다 (R54)."""
    grid = _FakeGrid(result=_gyeonggi_grid())
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)

    fetched = built["vacancy"]("202607")

    assert fetched.residuals["41"] == {"vacancy": 0, "seekers": 43823}


def test_sido_datasets_have_no_residual_concept(recorded_layout):
    rows, summaries = _vacancy_grid()
    grid = _FakeGrid(result=olap.ParsedGrid(
        [{"(근무지역)시도": "서울", "2026년 07월_유효구인인원(전체)": "1",
          "2026년 07월_유효구직자수(전체)": "1"}], []))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)
    assert built["vacancy_sido"]("202607").residuals is None


def test_group_subtotal_rows_are_not_reparented(recorded_layout):
    """실측으로 걸린 버그 — 소계 행이 일반구 이관에 먼저 닿으면 안 된다.

    '경기도 수원시 권선구 전체' 는 모시 후보가 '경기도 수원시 권선구' 가 돼
    예외를 때렸고(수집이 통째로 죽는다), 더 나쁜 '서울특별시 종로구 전체' 는
    앞부분이 실제 시군구라 조용히 종로구로 합쳐져 이중계상됐을 것이다."""
    grid = _gyeonggi_grid()
    label = "2026년 07월"
    for name in ("경기도 수원시 권선구 전체", "서울특별시 종로구 전체"):
        grid.rows.append({"(근무지역)시군구": name, "직종_중분류": name,
                          f"{label}_유효구인인원(전체)": "9,999",
                          f"{label}_유효구직자수(전체)": "9,999"})
    grid.rows.append({"(근무지역)시군구": "서울특별시 종로구",
                      "직종_중분류": "2025직종_경영·행정·사무직",
                      f"{label}_유효구인인원(전체)": "6",
                      f"{label}_유효구직자수(전체)": "95"})
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(),
                                      fetch=_FakeGrid(result=grid))

    rows = built["vacancy"]("202607").rows
    by_code = {r["sigungu"]: r for r in rows}

    assert by_code["11110"]["vacancy"] == 6       # 소계 9,999 가 섞이지 않았다
    assert by_code["41110"]["vacancy"] == 800     # 권선구 소계도 안 섞였다


def test_colspan_aggregate_row_is_not_counted_as_data(recorded_layout):
    """실측으로 잡은 값 오류 — 축 칸이 전부 같은 행은 리프가 아니라 집계 행이다.

    시군구 × 직종 그리드에 ['서울특별시 마포구', '서울특별시 마포구', 728, 5646]
    이 있었다(그룹이 페이지 경계에 걸려 헤더가 폭 전체로 다시 그려진 것으로 보인다).
    값이 마포구 전체 합이라 '… 전체' 규칙에 안 걸려 데이터 행으로 세어졌고,
    마포구가 정확히 두 배가 되면서 서울 시도 검산이 +728 초과했다."""
    rows, summaries = _vacancy_grid()
    rows.append({"(근무지역)시군구": "서울특별시 종로구", "직종_중분류": "서울특별시 종로구",
                 "2026년 07월_유효구인인원(전체)": "728",
                 "2026년 07월_유효구직자수(전체)": "5,646"})
    grid = _FakeGrid(result=olap.ParsedGrid(rows, summaries))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)

    by_code = {r["sigungu"]: r for r in built["vacancy"]("202607").rows}
    assert by_code["11110"]["vacancy"] == 6          # 728 이 더해지지 않았다


def test_mobility_rows_with_the_same_industry_on_both_axes_are_kept(recorded_layout):
    """축 셋인 mobility 에서 산업 == 산업(이전) 은 정상 행이다 — 오탐 금지."""
    label = "2026년 07월"
    rows = [{"(사업장)시도": "서울", "산업_대분류": "C 제조업",
             "산업(이전)_대분류": "C 제조업", f"{label}_경력이동자수(월)": "1,280"}]
    grid = _FakeGrid(result=olap.ParsedGrid(rows, []))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)

    out = built["mobility"]("202607").rows
    assert len(out) == 1 and out[0]["movers"] == 1280


def test_abolished_general_district_is_not_merged_into_its_parent(recorded_layout):
    """재리뷰 1 — 폐지 코드 41283(고양시 일산구)은 라벨이 3낱말이고 모시
    '경기도 고양시'(41280)가 실재해서, 이름으로 막지 않으면 배제되기는커녕
    조용히 고양시에 합산된다(후신 일산동구·일산서구까지 오면 이중계상)."""
    label = "2026년 07월"
    rows = [
        {"(근무지역)시군구": "경기도 고양시", "직종_중분류": "2025직종_경영·행정·사무직",
         f"{label}_유효구인인원(전체)": "100", f"{label}_유효구직자수(전체)": "200"},
        {"(근무지역)시군구": "경기도 고양시 일산구", "직종_중분류": "2025직종_경영·행정·사무직",
         f"{label}_유효구인인원(전체)": "9,999", f"{label}_유효구직자수(전체)": "9,999"},
        {"(근무지역)시군구": "경기도 고양시 일산동구", "직종_중분류": "2025직종_경영·행정·사무직",
         f"{label}_유효구인인원(전체)": "50", f"{label}_유효구직자수(전체)": "60"},
    ]
    grid = _FakeGrid(result=olap.ParsedGrid(rows, []))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)

    fetched = built["vacancy"]("202607")
    by_code = {r["sigungu"]: r for r in fetched.rows}

    assert by_code["41280"]["vacancy"] == 150        # 100 + 일산동구 50, 일산구는 빠진다
    assert "경기도 고양시 일산구" in str(fetchers.ABOLISHED_GENERAL_DISTRICTS)
    # 버려진 값은 사라지지 않고 잔여로 남아 시도 검산이 볼 수 있다
    assert fetched.residuals["41"]["vacancy"] == 9999


def test_duplicate_axis_rows_raise_when_no_reparenting_happened(recorded_layout):
    """재리뷰 4 — 이관이 없었으면 합칠 정상 중복도 없다. 그런데도 키가 겹치면
    그리드 중복·집계 행 누출이므로 조용히 더해 없애지 않고 실패한다."""
    label = "2026년 07월"
    row = {"(근무지역)시도": "서울", f"{label}_유효구인인원(전체)": "10",
           f"{label}_유효구직자수(전체)": "100"}
    grid = _FakeGrid(result=olap.ParsedGrid([row, dict(row)], []))
    built = fetchers.monthly_fetchers(browser=object(), cm=_CM(), get=_fake_get(), fetch=grid)

    with pytest.raises(fetchers.FetchError):
        built["vacancy_sido"]("202607")


def test_series_rows_do_not_gain_measure_fields_they_never_had(recorded_layout):
    """재리뷰 4 부수효과 — collect_insured_series 는 insured 만 낸다.
    병합이 돌면 없던 gained/lost 가 0 으로 생겼다."""
    label = "2026년 07월"
    rows = [{"(사업장)시도": name, f"{label}_피보험자수(전체)": "10"}
            for name in ("서울", "경기", "인천")]
    grid = _FakeGrid(result=olap.ParsedGrid(rows, []))
    built = fetchers.series_fetchers(["202607"], browser=object(), get=_fake_get(),
                                     fetch=grid, sleep=lambda s: None)

    out = built["insured_series"]()
    assert out and all("gained" not in row and "lost" not in row for row in out)
