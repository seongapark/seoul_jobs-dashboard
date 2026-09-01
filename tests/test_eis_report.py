from pathlib import Path
import pytest
from pipeline import eis_report

FIXTURE = Path(__file__).parent / "fixtures/eis_reptdtl.html"


class FakeResponse:
    def __init__(self, text):
        self.text = text


def test_reads_viewer_url_from_page():
    """reportId 를 하드코딩하지 않는다. EIS 가 재발급해도 안 깨지게."""
    html = FIXTURE.read_text(encoding="utf-8")
    url = eis_report.viewer_url("020010020", get=lambda u, **k: FakeResponse(html))
    assert url.startswith("https://eis.work24.go.kr/olap/report/viewer.do?")
    assert "reportId=" in url
    assert "&amp;" not in url  # 엔티티가 풀려 있어야 한다


def test_missing_input_raises():
    with pytest.raises(eis_report.EisReportError):
        eis_report.viewer_url("020010020", get=lambda u, **k: FakeResponse("<html></html>"))


def test_every_report_key_has_a_menu_id():
    for key in ["유효구인구직", "취업건수", "피보험자", "경력직이동"]:
        assert key in eis_report.REPORTS
        assert eis_report.REPORTS[key].isdigit()


def test_double_quoted_value_variant_parses():
    """EIS 가 따옴표 스타일을 바꿔도(단따옴표 id / 겹따옴표 value) 깨지지 않는다."""
    html = (
        "<input type=\"hidden\" id='reptIdUrl' name=\"reptIdUrl\" "
        "value=\"https://eis.work24.go.kr/olap/report/viewer.do?USER=abc"
        "&amp;reportId=ABC&amp;closYm=202607\" />"
    )
    url = eis_report.viewer_url("020010020", get=lambda u, **k: FakeResponse(html))
    assert "reportId=ABC" in url
    assert "&amp;" not in url


def test_sibling_reptIdUrlOpen_is_not_matched():
    """reptIdUrlOpen 만 있고 reptIdUrl 이 없으면 오매치하지 않고 에러를 낸다."""
    html = (
        "<input type=\"hidden\" id=\"reptIdUrlOpen\" name=\"reptIdUrlOpen\" "
        "value='https://eis.work24.go.kr/olap/report/viewer.do?reportId=SHOULD_NOT_MATCH' />"
    )
    with pytest.raises(eis_report.EisReportError):
        eis_report.viewer_url("020010020", get=lambda u, **k: FakeResponse(html))
