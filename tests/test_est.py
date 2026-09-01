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
    # objL3=ALL 요청에 직종별로 한 행씩, 각자 다른 C3 (예: keco2026_02) 를 달아
    # 돌려준다. obj_l3 파라미터를 그대로 되돌려주면 항상 "ALL" 이 되어 직종을
    # 구분할 수 없으므로, 실제 응답을 흉내내 C3 를 고정값으로 준다.
    def fake_fetch(table, *, item, obj_l1, obj_l2, obj_l3, periods, recent, api_key, get=None):
        return [{"PRD_DE": "202601", "DT": "26,828", "C1": obj_l1,
                 "C2": obj_l2, "C3": "keco2026_02", "ITM_ID": item}]

    rows = est.collect(["202601"], api_key="KEY", fetch=fake_fetch)
    row = next(r for r in rows
               if r["occupation"] == "02" and r["item"] == "채용계획인원"
               and r["sido"] == "11" and r["size"] == "전규모")
    assert row["value"] == 26828
    assert row["period"] == "202601"


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
    def fake_fetch(table, *, item, obj_l1, obj_l2, obj_l3, periods, recent, api_key, get=None):
        assert table == est.INDUSTRY_TABLE
        assert obj_l3 == "ALL"
        return [{"PRD_DE": "202601", "DT": "8,053",
                 "C1": obj_l1, "C2": obj_l2,
                 "C3": est.INDUSTRY_PREFIX + "11SCX0", "ITM_ID": item}]

    rows = est.collect_industry(["202601"], api_key="KEY", fetch=fake_fetch)
    row = next(r for r in rows
               if r["industry"] == "11SCX0" and r["item"] == "채용인원"
               and r["sido"] == "11" and r["size"] == "전규모")
    assert row["value"] == 8053
    assert row["period"] == "202601"
