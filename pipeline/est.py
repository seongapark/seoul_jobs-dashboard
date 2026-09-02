"""직종별사업체노동력조사 (KOSIS) 수집기.

표가 시기마다 갈린다. 더 성가신 것은 2026년 표에서 직종 코드 체계가
keco2018_ -> keco2026_ 로 바뀌고 항목 수도 182 -> 186 으로 늘었다는 점이다.
표를 이어 붙일 때 이 접두사를 갈아 끼우지 않으면 조용히 빈 응답이 온다.

산업별·규모별 표(DT_118N_DEN061)도 여기서 함께 수집한다. 주의: 규모 코드가
직종별 표와 다른 계열이다 — 직종별 표는 …322SIZES, 산업별 표는 …321SIZES 다.
직종별 표의 코드를 산업별 표에 그대로 갖다 쓰면 KOSIS 가 오류를 돌려준다.
"""
from __future__ import annotations

from pipeline import eis, kosis

TABLES = {
    "DT_118N_DEN052": {"first": "202101", "last": "202302", "keco": "keco2018_"},
    "DT_118N_DEN065": {"first": "202401", "last": "202502", "keco": "keco2018_"},
    "DT_118N_DEN062": {"first": "202601", "last": "299902", "keco": "keco2026_"},
}

ITEMS = {
    "13103110322DD_1": "현원",
    "13103110322DD_2": "구인인원",
    "13103110322DD_3": "채용인원",
    "13103110322DD_4": "미충원인원",
    "13103110322DD_5": "부족인원",
    "13103110322DD_6": "부족률",
    "13103110322DD_7": "채용계획인원",
}

# SIDO_CODE 는 KOSIS 자체 시도 코드 체계다 (obj_l1 로 그대로 요청에 나간다) —
# 이 값은 절대 바꾸지 않는다. KOSIS 기준 인천 "23", 경기 "31" 이다.
#
# Task 7b (R9, 컨트롤러 지시 정정): SIDO 는 그 KOSIS 코드를 EIS 가 쓰는
# 행정표준코드로 옮긴다. 이전에는 SIDO["23"]->"23", SIDO["31"]->"31" 처럼
# KOSIS 자체 코드를 그대로 내보냈는데, pipeline/eis.py 는 행정표준코드
# (서울 11110→11, 인천 28110→28, 경기 41110→41)를 쓴다. 두 표를 sido 로
# join/필터하면 인천·경기가 조용히 어긋났다. 그래서 이 값은 행정표준코드로
# 고정한다 — KOSIS 요청 코드(SIDO_CODE)와는 완전히 다른 목적의 표다.
SIDO = {"00": "00", "11": "11", "23": "28", "31": "41"}
SIDO_CODE = {"00": "15118REG2012_00", "11": "15118REG2012_11",
             "23": "15118REG2012_23", "31": "15118REG2012_31"}

SIZES = {
    "전규모": "13102110322SIZES.00",
    "5인미만": "13102110322SIZES.02",
    "5~9인": "13102110322SIZES.03",
    "10~29인": "13102110322SIZES.04",
    "30~99인": "13102110322SIZES.05",
    "100~299인": "13102110322SIZES.06",
    "300인이상": "13102110322SIZES.07",
}

INDUSTRY_TABLE = "DT_118N_DEN061"          # 산업별·규모별 (2024년 이후)
INDUSTRY_SIZES = {                          # 주의: 직종별 표와 규모 코드가 다르다 (…321 vs …322)
    "전규모": "13102110321SIZES.00",
    "5인미만": "13102110321SIZES.03",
    "5~9인": "13102110321SIZES.04",
    "10~29인": "13102110321SIZES.05",
    "30~99인": "13102110321SIZES.06",
    "100~299인": "13102110321SIZES.07",
    "300인이상": "13102110321SIZES.08",
}
INDUSTRY_PREFIX = "2026INDUSTRY_"


def table_for(period: str) -> str:
    for table, meta in TABLES.items():
        if meta["first"] <= period <= meta["last"]:
            return table
    raise ValueError(f"어느 표에도 없는 시점: {period}")


def occupation_code(period: str, keco: str) -> str:
    """특정 시점·직종에 대응하는 keco 코드를 돌려준다.

    표를 이어 붙일 때가 아니라, 직종 하나를 다시 조회할 때 쓰는 공개 헬퍼다.
    collect() 는 obj_l3="ALL" 로 통째로 받아오므로 이 함수를 호출하지 않는다.
    """
    return TABLES[table_for(period)]["keco"] + keco


def to_number(text):
    text = (text or "").strip().replace(",", "")
    if text in ("", "-", "None"):
        return None
    return int(float(text))


def _name(raw: dict):
    """raw 의 C3_NM(직종·산업 이름)을 정규화해서 돌려준다.

    실측(R40, 컨트롤러가 KOSIS 를 직접 불러 확인)으로 C3_NM 값이 코드
    접두("02 경영·행정·사무직")와 EIS 와 다른 구분자(ㆍ, U+318D)를 쓰는
    것이 드러났다 — eis.normalize_name() 을 거쳐야 두 출처의 이름이
    실제로 겹친다. 키가 아예 없으면 None 그대로 둔다(빈 문자열은 est 의
    실제 값과 헷갈린다, R33)."""
    value = raw.get("C3_NM")
    return eis.normalize_name(value) if value is not None else None


def collect(periods, *, api_key, fetch=kosis.fetch):
    rows = []
    for period in periods:
        table = table_for(period)
        for sido_key, sido_obj in SIDO_CODE.items():
            for size_name, size_obj in SIZES.items():
                for item_id, item_name in ITEMS.items():
                    payload = fetch(
                        table, item=item_id, obj_l1=sido_obj, obj_l2=size_obj,
                        obj_l3="ALL", periods=(period, period), recent=None,
                        api_key=api_key,
                    )
                    prefix = TABLES[table]["keco"]
                    for raw in payload:
                        value = to_number(raw.get("DT"))
                        if value is None:
                            continue
                        rows.append({
                            "period": raw.get("PRD_DE", period),
                            "sido": SIDO[sido_key],
                            "size": size_name,
                            "occupation": str(raw.get("C3", "")).replace(prefix, ""),
                            "occupation_name": _name(raw),
                            "item": item_name,
                            "value": value,
                        })
    return rows


def collect_industry(periods, *, api_key, fetch=kosis.fetch):
    rows = []
    for period in periods:
        for sido_key, sido_obj in SIDO_CODE.items():
            for size_name, size_obj in INDUSTRY_SIZES.items():
                for item_id, item_name in ITEMS.items():
                    payload = fetch(
                        INDUSTRY_TABLE, item=item_id, obj_l1=sido_obj, obj_l2=size_obj,
                        obj_l3="ALL", periods=(period, period), recent=None,
                        api_key=api_key,
                    )
                    for raw in payload:
                        value = to_number(raw.get("DT"))
                        if value is None:
                            continue
                        rows.append({
                            "period": raw.get("PRD_DE", period),
                            "sido": SIDO[sido_key],
                            "size": size_name,
                            "industry": str(raw.get("C3", "")).replace(INDUSTRY_PREFIX, ""),
                            "industry_name": _name(raw),
                            "item": item_name,
                            "value": value,
                        })
    return rows
