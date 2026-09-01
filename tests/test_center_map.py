from pathlib import Path
import pytest
from pipeline import center_map

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "data/center_map.json"


def test_70_sigungu_39_centers():
    cm = center_map.load(MAP)
    assert len(cm.codes()) == 70
    assert len(cm.centers()) == 39


def test_no_sigungu_belongs_to_two_centers():
    """이중배정은 센터별 합계를 부풀린다. 이 테스트가 그것만은 막는다."""
    cm = center_map.load(MAP)
    cm.validate()  # 어긋나면 ValueError


def test_known_assignments():
    cm = center_map.load(MAP)
    assert cm.center_of("11680") == "서울강남고용센터"   # 강남구
    assert cm.center_of("41590") == "화성고용센터"       # 화성시 통째
    assert cm.center_of("41820") == "춘천고용센터"       # 가평군은 강원지청 관할
    assert cm.center_of("28125") == "인천고용센터"       # 제물포구(신설)
    assert cm.center_of("28290") == "인천서부고용센터"   # 검단구(신설)


def test_gyeonggi_general_district_codes_are_absent():
    """41111 장안구 같은 일반구를 넣으면 수원시와 이중계상된다."""
    cm = center_map.load(MAP)
    for banned in ["41111", "41113", "41115", "41117", "41131", "41135"]:
        assert banned not in cm.codes()


def test_abolished_codes_are_absent():
    cm = center_map.load(MAP)
    for banned in ["41283", "41710", "41730", "41810"]:
        assert banned not in cm.codes()


def test_unknown_code_raises():
    cm = center_map.load(MAP)
    with pytest.raises(KeyError):
        cm.center_of("48170")  # 경남 통영시


def test_double_assignment_guard_fires(tmp_path):
    """load() 중에 이중배정을 감지하고 ValueError를 발생시킨다.

    같은 시군구 코드가 두 센터 아래 나타나면 load() 시점에 감지해야 한다.
    validate() 만으로는 부족하다 — 코드 스왑이나 타입으로 총 개수는 맞아도
    이중배정은 감지할 수 없다.
    """
    # 이중배정된 임시 매핑 파일 생성
    dup_mapping = {
        "version": "test",
        "기준": "test",
        "규칙": [],
        "센터": [
            {
                "센터": "센터A",
                "시도": "서울",
                "시군구": [
                    {"code": "11680", "name": "강남구"}
                ]
            },
            {
                "센터": "센터B",
                "시도": "경기",
                "시군구": [
                    {"code": "11680", "name": "강남구"}  # 동일한 코드
                ]
            }
        ]
    }

    import json
    tmp_file = tmp_path / "dup_map.json"
    tmp_file.write_text(json.dumps(dup_mapping), encoding="utf-8")

    # load() 호출 시 이중배정 감지 및 ValueError 발생
    with pytest.raises(ValueError) as exc_info:
        center_map.load(tmp_file)

    # 에러 메시지에 문제의 코드가 포함되어야 함
    assert "11680" in str(exc_info.value)
