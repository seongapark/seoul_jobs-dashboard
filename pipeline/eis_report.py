"""EIS 리포트의 현재 뷰어 주소를 찾는다.

reportId 는 EIS 가 재발급할 수 있어 하드코딩하지 않는다. 대신 메뉴 페이지가
숨은 input 'reptIdUrl' 에 현재 주소를 들고 있으므로 그것을 읽는다.
"""
from __future__ import annotations

import html as html_mod
import json
import re
from pathlib import Path

import requests

BASE = "https://eis.work24.go.kr/eisps/rpt/reptDtl.do"
UA = {"User-Agent": "Mozilla/5.0 (compatible; seoul-jobs-dashboard/1.0)"}

_CONFIG = json.loads((Path(__file__).resolve().parents[1] / "config/olap.json")
                     .read_text(encoding="utf-8"))
REPORTS: dict[str, str] = _CONFIG["reports"]

_PATTERN = re.compile(r"""id=["']reptIdUrl["'][^>]*?value=(["'])(.*?)\1""", re.S)


class EisReportError(RuntimeError):
    pass


def viewer_url(menu_id: str, *, get=requests.get) -> str:
    page = get(f"{BASE}?menuId={menu_id}", headers=UA, timeout=60).text
    found = _PATTERN.search(page)
    if not found:
        raise EisReportError(f"menuId={menu_id} 페이지에 reptIdUrl 이 없다 — 화면 개편 의심")
    return html_mod.unescape(found.group(2))
