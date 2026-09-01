"""pipeline.olap.parse_grid 순수 파서 테스트. 네트워크 접속 없음."""
import json
from pathlib import Path

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
