import pytest
from pipeline import eis
from pipeline import est


def test_table_switches_at_2026():
    """2026년부터 표가 갈리고 직종 코드 체계도 keco2018 -> keco2026 으로 바뀐다."""
    assert est.table_for("202502") == "DT_118N_DEN065"
    assert est.table_for("202601") == "DT_118N_DEN062"
    assert est.table_for("202302") == "DT_118N_DEN052"


def test_occupation_code_follows_the_table():
    assert est.occupation_code("202502", "02") == "keco2018_02"
    assert est.occupation_code("202601", "02") == "keco2026_02"
    assert est.occupation_code("202601", "") == "keco2026_"   # 전직종


def test_collect_shapes_rows():
    # collect() always queries with obj_l3="ALL" (전직종 일괄 조회) — 실제 KOSIS 는
    # objL3=ALL 요청 하나에 직종별로 여러 행을, 각자 다른 C3 (예: keco2026_02) 를
    # 달아 한꺼번에 돌려준다. 한 행짜리 fake 는 `for raw in payload:` 집계 경로를
    # 제대로 훈련시키지 못한다 — 첫 행만 남기고 나머지를 버리는 회귀가 있어도
    # 통과해버린다. 그래서 전직종·대분류·중분류가 섞인 다중 행 payload 를 쓰고,
    # DT 가 "-" 인 행(결측)이 걸러지는지도 같이 본다.
    # C3_NM 값은 R40 실측 그대로(2026-09-02, 컨트롤러가 KOSIS 를 직접 불러 확인) —
    # 코드 접두("02 ")와 한글 아래아(ㆍ, U+318D) 구분자가 실제로 이렇게 온다.
    def fake_fetch(table, *, item, obj_l1, obj_l2, obj_l3, periods, recent, api_key, get=None):
        return [
            {"PRD_DE": "202601", "DT": "109,560", "C1": obj_l1, "C2": obj_l2,
             "C3": "keco2026_", "C3_NM": "전직종", "ITM_ID": item},       # 전직종
            {"PRD_DE": "202601", "DT": "31,049", "C1": obj_l1, "C2": obj_l2,
             "C3": "keco2026_0", "C3_NM": "0 경영ㆍ사무ㆍ금융ㆍ보험직", "ITM_ID": item},  # 0 대분류
            {"PRD_DE": "202601", "DT": "26,828", "C1": obj_l1, "C2": obj_l2,
             "C3": "keco2026_02", "C3_NM": "02 경영ㆍ행정ㆍ사무직", "ITM_ID": item},      # 02 중분류
            {"PRD_DE": "202601", "DT": "-", "C1": obj_l1,
             "C2": obj_l2, "C3": "keco2026_99", "ITM_ID": item},     # 결측 -> 버려져야 함
            {"PRD_DE": "202601", "DT": "7", "C1": obj_l1, "C2": obj_l2,
             "C3": "keco2026_03", "ITM_ID": item},   # C3_NM 없음 -> None 이어야 함
        ]

    rows = est.collect(["202601"], api_key="KEY", fetch=fake_fetch)
    matches = [r for r in rows
               if r["item"] == "채용계획인원" and r["sido"] == "11" and r["size"] == "전규모"]

    # 결측(DT="-") 행 하나는 버려지고 나머지 4행만 남아야 한다.
    assert len(matches) == 4
    assert {r["occupation"] for r in matches} == {"", "0", "02", "03"}
    assert "99" not in {r["occupation"] for r in matches}

    values = {r["occupation"]: r["value"] for r in matches}
    assert values == {"": 109560, "0": 31049, "02": 26828, "03": 7}
    assert all(r["period"] == "202601" for r in matches)

    # 이름은 코드 접두가 빠지고 구분자가 · (U+00B7) 로 통일된 채 실려야 한다(R40).
    names = {r["occupation"]: r["occupation_name"] for r in matches}
    assert names == {
        "": "전직종", "0": "경영·사무·금융·보험직", "02": "경영·행정·사무직", "03": None,
    }


def test_sido_object_codes_map_to_the_administrative_standard_code_eis_uses():
    """Task 7b (R9): KOSIS 요청 코드(est.SIDO_CODE 의 15118REG2012_* 접미사)는
    KOSIS 자체 시도 코드 체계다 — 인천은 "23", 경기는 "31" 이다. 그런데 EIS
    행은 행정표준코드(서울 11, 인천 28, 경기 41)를 쓴다. 두 표를 join 하려면
    est 가 내보내는 "sido" 값도 행정표준코드여야 한다 — KOSIS 자체 코드를 그대로
    돌려주면(이전 버그: "23"->"23", "31"->"31") 화면의 sido 필터가 안 맞는다."""
    assert est.SIDO == {"00": "00", "11": "11", "23": "28", "31": "41"}
    # KOSIS 요청 코드(SIDO_CODE) 자체는 바뀌면 안 된다 — obj_l1 로 그대로 나간다.
    assert est.SIDO_CODE == {
        "00": "15118REG2012_00", "11": "15118REG2012_11",
        "23": "15118REG2012_23", "31": "15118REG2012_31",
    }


def test_est_and_eis_agree_on_the_three_metro_sido_codes():
    """est(KOSIS)와 eis(행 데이터) 두 수집기가 서로 다른 행정표준코드를 내보내면
    화면에서 sido 로 join/필터할 때 조용히 어긋난다 — 이 테스트가 그 드리프트를
    영구히 막는다."""
    assert est.SIDO["11"] == eis._SIDO_NAME_TO_CODE["서울"] == "11"
    assert est.SIDO["23"] == eis._SIDO_NAME_TO_CODE["인천"] == "28"
    assert est.SIDO["31"] == eis._SIDO_NAME_TO_CODE["경기"] == "41"
    assert est.SIDO["00"] == eis._SIDO_NAME_TO_CODE["전국"] == "00"


def test_value_strips_commas_and_handles_blank():
    assert est.to_number("26,828") == 26828
    assert est.to_number("-") is None
    assert est.to_number("") is None


def test_industry_sizes_use_321_size_family():
    """산업별 표는 규모 코드가 …321 계열이다. 직종별 표의 …322 코드를 쓰면 KOSIS 가
    오류를 돌려준다 — 그래서 두 표는 규모 코드를 따로 관리한다."""
    for size_code in est.INDUSTRY_SIZES.values():
        assert "13102110321SIZES." in size_code
    # 직종별 표의 SIZES 는 다른 계열이어야 한다 (…322).
    for size_code in est.SIZES.values():
        assert "13102110322SIZES." in size_code
    assert est.INDUSTRY_SIZES["전규모"] == "13102110321SIZES.00"


def test_collect_industry_shapes_rows():
    # collect() 테스트와 같은 이유로, 산업별 objL3=ALL 응답도 산업별로 여러 행이
    # 한 번에 온다 (전산업 총계·대분류·다른 대분류가 섞여서). 한 행짜리 fake 로는
    # `for raw in payload:` 집계 경로가 훈련되지 않는다.
    def fake_fetch(table, *, item, obj_l1, obj_l2, obj_l3, periods, recent, api_key, get=None):
        assert table == est.INDUSTRY_TABLE
        assert obj_l3 == "ALL"
        return [
            {"PRD_DE": "202601", "DT": "1,234,567", "C1": obj_l1, "C2": obj_l2,
             "C3": est.INDUSTRY_PREFIX + "11S000", "C3_NM": "전산업", "ITM_ID": item},
            {"PRD_DE": "202601", "DT": "8,053", "C1": obj_l1, "C2": obj_l2,
             "C3": est.INDUSTRY_PREFIX + "11SCX0", "C3_NM": "제조업", "ITM_ID": item},
            {"PRD_DE": "202601", "DT": "421", "C1": obj_l1, "C2": obj_l2,
             "C3": est.INDUSTRY_PREFIX + "11SDX0", "C3_NM": "전기가스업", "ITM_ID": item},
            {"PRD_DE": "202601", "DT": "-", "C1": obj_l1,
             "C2": obj_l2, "C3": est.INDUSTRY_PREFIX + "11SZZ0", "ITM_ID": item},  # 결측 -> 버려져야 함
            {"PRD_DE": "202601", "DT": "3", "C1": obj_l1, "C2": obj_l2,
             "C3": est.INDUSTRY_PREFIX + "11SEX0", "ITM_ID": item},  # C3_NM 없음 -> None 이어야 함
        ]

    rows = est.collect_industry(["202601"], api_key="KEY", fetch=fake_fetch)
    matches = [r for r in rows
               if r["item"] == "채용인원" and r["sido"] == "11" and r["size"] == "전규모"]

    # 결측(DT="-") 행 하나는 버려지고 나머지 4행만 남아야 한다.
    assert len(matches) == 4
    assert {r["industry"] for r in matches} == {"11S000", "11SCX0", "11SDX0", "11SEX0"}
    assert "11SZZ0" not in {r["industry"] for r in matches}

    values = {r["industry"]: r["value"] for r in matches}
    assert values == {"11S000": 1234567, "11SCX0": 8053, "11SDX0": 421, "11SEX0": 3}
    assert all(r["period"] == "202601" for r in matches)

    names = {r["industry"]: r["industry_name"] for r in matches}
    assert names == {"11S000": "전산업", "11SCX0": "제조업", "11SDX0": "전기가스업", "11SEX0": None}
