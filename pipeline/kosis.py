"""KOSIS OpenAPI 클라이언트.

주의: 직종별사업체노동력조사는 반기 자료이고 주기 코드는 'S' 다. 'H' 로 부르면
KOSIS 가 '필수요청변수값이 누락되었습니다'(err 20) 를 돌려준다 — 원인을 짚기
어려운 오류라 여기 한 곳에 못 박아 둔다.
"""
from __future__ import annotations

import requests

API = "https://kosis.kr/openapi/statisticsData.do"
ORG_ID = "118"


class KosisError(RuntimeError):
    pass


def fetch(table, *, item, obj_l1, obj_l2, obj_l3,
          periods=None, recent=None, api_key, get=requests.get):
    params = {
        "method": "getList", "apiKey": api_key, "orgId": ORG_ID, "tblId": table,
        "itmId": item, "objL1": obj_l1, "objL2": obj_l2, "objL3": obj_l3,
        "prdSe": "S", "format": "json", "jsonVD": "Y",
    }
    if periods:
        params["startPrdDe"], params["endPrdDe"] = periods
    else:
        params["newEstPrdCnt"] = str(recent or 1)

    payload = get(API, params=params, timeout=120).json()
    if isinstance(payload, dict):
        raise KosisError(payload.get("errMsg", str(payload)))
    return payload
