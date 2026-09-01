import pytest
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
    def fake_fetch(table, *, item, obj_l1, obj_l2, obj_l3, periods, recent, api_key, get=None):
        return [
            {"PRD_DE": "202601", "DT": "109,560", "C1": obj_l1,
             "C2": obj_l2, "C3": "keco2026_", "ITM_ID": item},       # 전직종
            {"PRD_DE": "202601", "DT": "31,049", "C1": obj_l1,
             "C2": obj_l2, "C3": "keco2026_0", "ITM_ID": item},      # 0 대분류
            {"PRD_DE": "202601", "DT": "26,828", "C1": obj_l1,
             "C2": obj_l2, "C3": "keco2026_02", "ITM_ID": item},     # 02 중분류
            {"PRD_DE": "202601", "DT": "-", "C1": obj_l1,
             "C2": obj_l2, "C3": "keco2026_99", "ITM_ID": item},     # 결측 -> 버려져야 함
        ]

    rows = est.collect(["202601"], api_key="KEY", fetch=fake_fetch)
    matches = [r for r in rows
               if r["item"] == "채용계획인원" and r["sido"] == "11" and r["size"] == "전규모"]

    # 결측(DT="-") 행 하나는 버려지고 나머지 3행만 남아야 한다.
    assert len(matches) == 3
    assert {r["occupation"] for r in matches} == {"", "0", "02"}
    assert "99" not in {r["occupation"] for r in matches}

    values = {r["occupation"]: r["value"] for r in matches}
    assert values == {"": 109560, "0": 31049, "02": 26828}
    assert all(r["period"] == "202601" for r in matches)


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
            {"PRD_DE": "202601", "DT": "1,234,567", "C1": obj_l1,
             "C2": obj_l2, "C3": est.INDUSTRY_PREFIX + "11S000", "ITM_ID": item},  # 전산업
            {"PRD_DE": "202601", "DT": "8,053", "C1": obj_l1,
             "C2": obj_l2, "C3": est.INDUSTRY_PREFIX + "11SCX0", "ITM_ID": item},  # C.제조업
            {"PRD_DE": "202601", "DT": "421", "C1": obj_l1,
             "C2": obj_l2, "C3": est.INDUSTRY_PREFIX + "11SDX0", "ITM_ID": item},  # D.전기가스업
            {"PRD_DE": "202601", "DT": "-", "C1": obj_l1,
             "C2": obj_l2, "C3": est.INDUSTRY_PREFIX + "11SZZ0", "ITM_ID": item},  # 결측 -> 버려져야 함
        ]

    rows = est.collect_industry(["202601"], api_key="KEY", fetch=fake_fetch)
    matches = [r for r in rows
               if r["item"] == "채용인원" and r["sido"] == "11" and r["size"] == "전규모"]

    # 결측(DT="-") 행 하나는 버려지고 나머지 3행만 남아야 한다.
    assert len(matches) == 3
    assert {r["industry"] for r in matches} == {"11S000", "11SCX0", "11SDX0"}
    assert "11SZZ0" not in {r["industry"] for r in matches}

    values = {r["industry"]: r["value"] for r in matches}
    assert values == {"11S000": 1234567, "11SCX0": 8053, "11SDX0": 421}
    assert all(r["period"] == "202601" for r in matches)
