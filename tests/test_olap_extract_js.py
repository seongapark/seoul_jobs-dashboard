"""olap._EXTRACT_JS 자체를 실제 브라우저에서 돌려 중첩 세로 헤더 전개를 검증한다.

**네트워크에 나가지 않는다** — `page.set_content()` 로 로컬 HTML 문자열만 띄운다.
다른 테스트들의 가짜 page 는 `evaluate()` 에서 이미 구운 `[header, *body]` 를
돌려주므로 이 JS 가 한 번도 실행되지 않았다(리뷰 Important 4). 여기서 실행한다.

HTML 은 실측(2026-09-02)한 DOM 모양을 본뜬다: 바깥 레벨은 rowspan 으로 그룹 첫
행에만 그려지고, 총계 행은 colspan 으로 레벨 전체를 덮는다.
"""
import pytest

from pipeline import olap

pytest.importorskip("playwright.sync_api")

NESTED_HTML = """
<div class="dx-pivotgrid">
  <div class="dx-area-description-cell">
    <div class="dx-area-field-content">(근무지역)시군구</div>
    <div class="dx-area-field-content">직종_중분류</div>
  </div>
  <table>
    <thead class="dx-pivotgrid-horizontal-headers">
      <tr><td colspan="2">2026년 07월</td></tr>
      <tr><td>유효구인인원(전체)</td><td>유효구직자수(전체)</td></tr>
    </thead>
    <tbody class="dx-pivotgrid-vertical-headers">
      <tr><td colspan="2">총계</td></tr>
      <tr><td rowspan="2">서울특별시 종로구</td><td>관리직</td></tr>
      <tr><td>사무직</td></tr>
      <tr><td>서울특별시 중구</td><td>관리직</td></tr>
      <tr><td colspan="2">사무직</td></tr>
    </tbody>
  </table>
  <div class="dx-pivotgrid-area-data">
    <table><tbody>
      <tr><td>165,821</td><td>1,550,154</td></tr>
      <tr><td>6</td><td>95</td></tr>
      <tr><td>11</td><td>120</td></tr>
      <tr><td>3</td><td>80</td></tr>
      <tr><td>777</td><td>888</td></tr>
    </tbody></table>
  </div>
</div>
"""


@pytest.fixture(scope="module")
def extracted():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as error:  # noqa: BLE001 — 브라우저 미설치 환경은 건너뛴다
            pytest.skip(f"chromium 을 못 띄운다: {error!r}")
        try:
            page = browser.new_page()
            page.set_content(NESTED_HTML)      # 네트워크 없음
            yield page.evaluate(olap._EXTRACT_JS)
        finally:
            browser.close()


def test_header_names_every_row_axis_level_then_the_measures(extracted):
    assert extracted[0] == ["(근무지역)시군구", "직종_중분류",
                            "2026년 07월_유효구인인원(전체)",
                            "2026년 07월_유효구직자수(전체)",
                            olap.AGGREGATE_COLUMN]


def test_rowspan_on_the_outer_level_is_carried_into_following_rows(extracted):
    """바깥 레벨은 그룹 첫 행에만 그려진다 — 안 펴면 대부분의 행이 리프 하나뿐이다."""
    assert extracted[2] == ["서울특별시 종로구", "관리직", "6", "95", "0"]
    assert extracted[3] == ["서울특별시 종로구", "사무직", "11", "120", "0"]


def test_colspan_on_the_total_row_fills_every_level(extracted):
    assert extracted[1] == ["총계", "총계", "165,821", "1,550,154", "1"]


def test_a_new_group_starts_a_fresh_outer_label(extracted):
    assert extracted[4] == ["서울특별시 중구", "관리직", "3", "80", "0"]


def test_no_cell_is_left_blank(extracted):
    """빈 칸은 checks.check_axis_values 가 잡는 degradation 의 형태다 — 정상 표에는 없다."""
    assert all("" not in row for row in extracted)


def test_a_cell_that_spans_row_axis_levels_is_marked_as_an_aggregate(extracted):
    """실측(2026-09-03, 경력직이동 3·4페이지 경계): **같은 소계 행이 페이지 경계에서
    두 번, 다르게 그려진다.**

        3페이지 마지막: td('11차_숙박 및 음식점업', colspan=2)            → 18,596
        4페이지 tr[2] : td('11차_숙박 및 음식점업 전체', colspan=2, total) → 18,596

    앞엣것은 잘린 렌더라 ' 전체' 접미도 `dx-row-total` 클래스도 없다. 그래서
    텍스트로는 **진짜 리프와 구별할 수 없다** — 경력직이동에서 산업==산업(이전)인
    리프는 정상이기 때문이다(숙박→숙박 11,343 이 실제로 따로 있다). 아홉 번째
    실측 수집이 그 둘을 같은 축의 두 행으로 보고 죽었다.

    신뢰할 수 있는 신호는 구조다: **행 축 레벨 여럿을 colspan 으로 덮은 셀은
    집계 행이고, 진짜 리프는 레벨마다 자기 td 를 갖는다.** R54 의 "축 칸이 전부
    같은 값" 규칙은 그 신호를 텍스트로 추정한 것이라, colspan 이 일부 레벨만
    덮으면 놓친다. 추출기가 그 사실을 그대로 넘긴다.
    """
    header = extracted[0]
    assert header[-1] == olap.AGGREGATE_COLUMN

    marks = {tuple(row[:2]): row[-1] for row in extracted[1:]}
    assert marks[("총계", "총계")] == "1"                 # colspan 이 레벨 전부를 덮는다
    assert marks[("사무직", "사무직")] == "1"              # 경계에서 잘린 소계
    assert marks[("서울특별시 종로구", "관리직")] == "0"     # 진짜 리프
    assert marks[("서울특별시 중구", "관리직")] == "0"
