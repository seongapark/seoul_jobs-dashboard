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
