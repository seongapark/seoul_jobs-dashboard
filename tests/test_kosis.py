import pytest
from pipeline import kosis


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_uses_half_year_period_code():
    """반기는 S 다. H 로 부르면 KOSIS 가 '필수요청변수 누락'을 돌려준다."""
    seen = {}

    def get(url, params, timeout):
        seen.update(params)
        return FakeResponse([{"PRD_DE": "202601", "DT": "109560"}])

    kosis.fetch("DT_118N_DEN062", item="13103110322DD_7",
                obj_l1="15118REG2012_11", obj_l2="13102110322SIZES.00",
                obj_l3="keco2026_", recent=1, periods=None,
                api_key="KEY", get=get)
    assert seen["prdSe"] == "S"
    assert seen["objL3"] == "keco2026_"


def test_returns_rows():
    def get(url, params, timeout):
        return FakeResponse([{"PRD_DE": "202601", "DT": "109560", "C3": "keco2026_"}])

    rows = kosis.fetch("DT_118N_DEN062", item="13103110322DD_7",
                       obj_l1="15118REG2012_11", obj_l2="13102110322SIZES.00",
                       obj_l3="keco2026_", recent=1, periods=None,
                       api_key="KEY", get=get)
    assert rows[0]["DT"] == "109560"


def test_error_payload_raises():
    def get(url, params, timeout):
        return FakeResponse({"err": "20", "errMsg": "필수요청변수값이 누락되었습니다."})

    with pytest.raises(kosis.KosisError) as e:
        kosis.fetch("DT_118N_DEN062", item="x", obj_l1="y", obj_l2="z",
                    obj_l3="w", recent=1, periods=None, api_key="KEY", get=get)
    assert "누락" in str(e.value)
