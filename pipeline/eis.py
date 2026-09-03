"""EIS OLAP 네 리포트를 화면이 쓰는 행 모양으로 편다.

지역 축 선택이 이 모듈의 핵심 판단이다. 유효구인구직은 (근무지역) 축을 쓴다 —
구인은 모집 근무지, 구직은 희망 근무지라 둘이 같은 잣대가 된다. 피보험자는
(사업장) 축뿐이라 선택의 여지가 없다.

Task 7 Step 0 탐침(2026-09-01) 결정 — (근무지역)시군구 × 직종 중·소분류를 얻는 법:
  기본 레이아웃은 이 모양을 안 준다 (유효구인구직현황(전체) 은 행=(지역별)시도,
  열=마감년월). 세 경로를 확인했다.

  1) 다른 리포트: 050010060 "직종별 유효구인구직현황(전체)" 은 기본 레이아웃이
     마감년월 x 직종_중분류 x 직종_소분류로 원하는 모양에 가까워 보였지만,
     지역 필터(툴바 "지역" 드롭다운, DOM: `#param_CTPV_CD_8978`)가 **시도
     수준까지만** 간다 (드롭다운 목록에 시군구 항목이 없음, 17개 시도만).
     → 폐기.
  2) URL 파라미터: 뷰어 URL은 `USER,assign_name,dataScroll,reportId,closYm`
     만 받는다. 지역/레이아웃을 URL로 지정하는 파라미터는 발견하지 못했다
     (지역 드롭다운은 JS 로 채워지는 읽기전용 텍스트박스라 URL 값을 안 읽는
     것으로 보인다). → 폐기.
  3) UI 조작(채택): 기본 리포트(020010020) 좌측 "분석 항목" 트리에 (근무지역)
     시도/시군구, 직종_중분류/소분류, 산업_대분류 필드가 전부 있다. 행 영역
     초기화(`#rowAdHocList1_5990_clear`) 후 (근무지역)시군구, 직종_중분류를
     드래그해 행 영역에 순서대로 넣고(`#rowAdHocList1_5990`), 돋보기(검색)를
     눌러 재조회하면 실제로 (근무지역)시군구 × 직종_중분류 중첩 표가 나온다
     (`tools/probe_field_relocation.py` 로 확인, 실측 헤더 "직종_중분류"/
     "(근무지역)시군구" 두 필드, 리프 행 예: "서울특별시 종로구"). **깨지는
     조건**: EIS 가 이 커스텀 jQuery-UI 필드초이서("WISE" 위젯, 클래스
     `wise-area-field`, id 접미사 `_5990`)를 바꾸거나 필드의 `uni_nm` 속성값
     ("(근무지역)시군구" 등)을 바꾸면 셀렉터가 깨진다. 매우 깨지기 쉽다 —
     매달 정기 수집에 쓰려면 이 UI 조작을 Playwright 스크립트로 고정해야
     하는데, 이번 Task 7 범위에서는 하지 않았다 (후속 과제로 남김, 아래
     "우려" 참고).

  덤으로 발견한 것 — 가상화 질문(Task 6 이 남긴 것): (근무지역)시군구 같은
  큰 행 축은 무한 스크롤이 아니라 **페이지네이션**(`.dx-datagrid-pager`)으로
  나뉜다. (지역별)시군구 단독(~250행)만 놓아도 페이지 6개였다. `olap.fetch_grid`
  는 이제 페이지가 2개 이상이면 스크롤을 시도하기도 전에 `OlapPaginationError`
  를 낸다 (Task 7 에서 추가) — 예전처럼 첫 페이지만 조용히 반환하지 않는다.

  실측으로 바로잡은 것 하나 더: 브리프 예시 코드는 유효구직 측정값 컬럼명을
  "유효구직건수(전체)"로 가정했지만, 실제 OLAP 그리드 헤더는
  "유효구직자수(전체)"다 (`tests/fixtures/olap_grid.json`,
  2026년 07월 실뷰어 캡처: `"2026년 07월_유효구직자수(전체)"`). 그런데 Task 7
  브리프의 단위 테스트(`tests/test_eis.py`)는 가짜 행 딕셔너리를 직접 만들며
  "유효구직건수(전체)" 라는 키를 쓴다 — 테스트가 계약이므로 그 키도 읽어야
  하고, 실데이터도 죽지 않게 실제 헤더 이름도 읽어야 한다. 그래서
  collect_vacancy 는 두 이름을 순서대로 시도한다 (`_SEEKERS_KEYS`) — 어느
  한쪽이 없으면 조용히 0이 되는 대신 있는 쪽을 쓴다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_NAMES: dict[str, str] = json.loads(
    (Path(__file__).resolve().parents[1] / "data/sigungu_names.json")
    .read_text(encoding="utf-8")
)
# R2b: 모듈 임포트 시 한 번만 만든다 — 빈 dict 를 선언해 뒀다가 나중에 채우지 않는다.
SIGUNGU_NAME_TO_CODE: dict[str, str] = {name: code for code, name in _NAMES.items()}

# 브리프가 가정한 이름과 실제 OLAP 헤더 이름이 다르다 (위 docstring 참고).
# 브리프 쪽을 먼저 시도해 주어진 단위 테스트를 만족하고, 실데이터 쪽도 시도해
# 조용히 0이 되는 일을 막는다.
_SEEKERS_KEYS = ("유효구직건수(전체)", "유효구직자수(전체)")


class UnknownRegion(ValueError):
    """지역 이름을 시군구 코드로 못 옮겼을 때 낸다.

    모르는 지역을 조용히 버리면 합계가 어긋난 채 배포된다 — 절대 조용히
    넘어가지 않는다.
    """


def period_code(text: str) -> str:
    found = re.search(r"(\d{4})년\s*(\d{2})월", text or "")
    if not found:
        raise ValueError(f"기간을 못 읽는다: {text!r}")
    return found.group(1) + found.group(2)


def to_number(text) -> int:
    text = (text or "").strip().replace(",", "")
    return 0 if text in ("", "-") else int(float(text))


def _first(row: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in row:
            return row[key]
    return None


def _code(name: str) -> str:
    try:
        return SIGUNGU_NAME_TO_CODE[(name or "").strip()]
    except KeyError:
        raise UnknownRegion(f"매핑에 없는 지역: {name!r}") from None


def _strip_prefix(text: str) -> str:
    return re.sub(r"^\d{4}직종_", "", (text or "").strip())


def normalize_name(text: str) -> str:
    """직종·산업 이름을 est(KOSIS)·eis 두 출처가 같은 값으로 비교할 수 있게 만든다.

    R40 실측(컨트롤러가 KOSIS 를 직접 불러 확인, 2026-09-02)으로 드러난
    두 가지 차이를 없앤다 — 이걸 안 하면 두 출처의 이름이 하나도 안 겹쳐
    "조용한 미조인"이 그대로 남는다(R33 이 없애려던 바로 그 문제):

      - KOSIS 이름은 코드 접두가 붙는다(``"02 경영·행정·사무직"``, ``"9 농림어업직"``).
        EIS 이름에는 접두가 없다.
      - 구분자 문자가 다르다 — KOSIS 는 한글 아래아(ㆍ, U+318D)나 반각 카타카나
        가운뎃점(･, U+FF65)을 쓰고, EIS 는 가운뎃점(·, U+00B7)을 쓴다. 화면에서는
        거의 구별이 안 되지만 다른 코드포인트라 문자열 비교가 조용히 실패한다.

    코드 접두가 없는 이름("전직종")은 숫자가 없으니 그대로 남는다.

    R72 실측(2026-09-03) — **산업 축에도 같은 종류의 접두 차이가 있다.** 위
    규칙은 직종만 없앴고 산업은 두 출처가 하나도 안 겹친 채였다(반기 수집의
    이름 겹침 검사가 잡았다):

      - EIS 는 분류 개정 표시를 붙인다: ``"11차_광업(05~08)"``.
      - KOSIS 는 분류 코드를 붙인다: 대분류 ``"B.광업(05~08)"``,
        중분류 ``"B05 석탄 원유 및 천연가스 광업"``.

    접두를 떼면 대분류끼리 같은 값이 된다(``"광업(05~08)"``). 중분류 이름은
    떼어도 EIS 대분류와 안 겹치는데, 그건 실제로 다른 층위라서 맞다.
    """
    text = (text or "").strip()
    text = text.replace("ㆍ", "·").replace("･", "·")
    text = re.sub(r"^\d+차_", "", text)            # EIS 산업: "11차_"
    text = re.sub(r"^[A-Z]\.", "", text)           # KOSIS 산업 대분류: "B."
    text = re.sub(r"^[A-Z]\d{2}\s+", "", text)     # KOSIS 산업 중분류: "B05 "
    text = re.sub(r"^\d+\s+", "", text)            # KOSIS 직종: "02 "
    return re.sub(r"\s+", " ", text).strip()


def collect_vacancy(rows, cm) -> list[dict]:
    """(근무지역)시군구 축 유효구인구직 행을 화면용 행으로 편다."""
    out = []
    for row in rows:
        code = _code(row["(근무지역)시군구"])
        out.append({
            "period": period_code(row["마감년월"]),
            "sigungu": code,
            "center": cm.center_of(code),
            "occupation": normalize_name(_strip_prefix(row.get("직종_중분류", ""))),
            "industry": normalize_name(row.get("산업_대분류")),
            "vacancy": to_number(row.get("유효구인인원(전체)")),
            "seekers": to_number(_first(row, _SEEKERS_KEYS)),
        })
    return out


def collect_placement(rows, cm) -> list[dict]:
    """(근무지역)시군구 축 취업건수 행을 화면용 행으로 편다."""
    out = []
    for row in rows:
        code = _code(row["(근무지역)시군구"])
        out.append({
            "period": period_code(row["마감년월"]),
            "sigungu": code,
            "center": cm.center_of(code),
            "occupation": normalize_name(_strip_prefix(row.get("직종_중분류", ""))),
            "placements": to_number(row.get("취업건수(월)")),
        })
    return out


def collect_insured(rows, cm) -> list[dict]:
    """(사업장)시군구 축 피보험자 행을 화면용 행으로 편다 (지역 축 선택지가 없다)."""
    out = []
    for row in rows:
        code = _code(row["(사업장)시군구"])
        out.append({
            "period": period_code(row["마감년월"]),
            "sigungu": code,
            "center": cm.center_of(code),
            "occupation": normalize_name(_strip_prefix(row.get("직종_중분류", ""))),
            "industry": normalize_name(row.get("산업_대분류")),
            "insured": to_number(row.get("피보험자수(전체)")),
            "gained": to_number(row.get("취득자수(월)")),
            "lost": to_number(row.get("상실자수(월)")),
        })
    return out


def collect_mobility(rows) -> list[dict]:
    """시도 축 경력직 이동 행을 화면용 행으로 편다 (센터 매핑이 필요 없다).

    다른 시도 축 수집기(collect_vacancy_sido 등)와 같이 sido_code() 로
    행정표준코드를 낸다 — 이름("서울")을 그대로 두면 est.py 와 join 이
    안 되고, 수도권 밖 시도가 섞여도 조용히 넘어간다(R35).
    """
    return [{
        "period": period_code(row["마감년월"]),
        "sido": sido_code(row.get("(사업장)시도")),
        "industry": normalize_name(row.get("산업_대분류")),
        "prev_industry": normalize_name(row.get("산업(이전)_대분류")),
        "movers": to_number(row.get("경력이동자수(월)")),
    } for row in rows]


# ---------------------------------------------------------------------------
# R4 — 시도 단위 값은 시군구 합으로 만들지 않는다.
#
# 유효구직건수는 1인이 여러 건을 낼 수 있어(1인 다건) 시군구별 값을 더하면
# 시도 총계보다 커진다. 그래서 시도 총계가 필요한 화면은 시군구를 더하는 대신
# 이 함수들로 **시도 단위 그리드를 따로** 읽는다. 반환 행에는 sigungu/center
# 가 없고 대신 sido 코드("11"=서울, "41"=경기, "28"=인천, "00"=전국 총계)가
# 있다 — 시군구 코드 체계(SIGUNGU_NAME_TO_CODE)와 헷갈리지 않도록 완전히
# 다른 필드명을 쓴다.
# ---------------------------------------------------------------------------

# 축마다 시도 이름 표기가 다르다 — 실측(2026-09-03): **(근무지역)시도** 는
# '서울'·'경기'·'인천' 처럼 짧게 오고, **(사업장)시도** 는 '서울특별시'·'경기도'·
# '인천광역시' 처럼 행정 정식명으로 온다. 짧은 이름만 알던 표 때문에 여덟 번째
# 실측 수집에서 `insured_sido` 는 '총계' 한 행만 남고(수도권 시도가 통째로
# 사라졌다) `mobility` 는 0행이 됐다 — `check_sido_coverage` 가 잡아 줬다.
# 두 표기를 다 받는다.
#
# 주의: 이 표는 **시도 축 데이터셋에만** 쓰인다(`_split_metro` 가 `spec.sido_axis`
# 로 고른다). 시군구 축에서 같은 정식명이 나타나는 행은 "시도까지만 적은 건"
# (시도 레벨 잔여 멤버)이라 잔여로 가야 하고, 그쪽은 `SIGUNGU_NAME_TO_CODE` 를
# 보므로 여기 추가해도 영향이 없다.
_SIDO_NAME_TO_CODE = {
    "총계": "00",
    "전국": "00",
    "서울": "11",
    "서울특별시": "11",
    "경기": "41",
    "경기도": "41",
    "인천": "28",
    "인천광역시": "28",
}


def sido_code(name: str) -> str:
    try:
        return _SIDO_NAME_TO_CODE[(name or "").strip()]
    except KeyError:
        raise UnknownRegion(f"수도권(서울/경기/인천) 밖 시도이거나 매핑에 없다: {name!r}") from None


class WrongAxis(KeyError):
    """기대한 지역 축 컬럼이 그리드에 없을 때 낸다 (R45).

    옛 컬럼 이름과 새 컬럼 이름을 둘 다 받아들이면 **틀린 축을 조용히
    통과시키는 길**이 된다 — 에러도 크래시도 없이 축만 틀린 파일이 배포되는,
    이 프로젝트에서 가장 나쁜 실패 모양이다. 그래서 대체 이름을 찾지 않고
    없으면 바로 실패한다.
    """


def _axis(row: dict, column: str) -> str:
    try:
        return row[column]
    except KeyError:
        raise WrongAxis(
            f"기대한 지역 축 컬럼 {column!r} 이 없다 — 레이아웃이 다른 축으로 "
            f"잡혔을 수 있다. 실제 컬럼: {sorted(row)}") from None


# ---------------------------------------------------------------------------
# R45 (Task 15a 실측, 2026-09-02) — 시도 축도 **(근무지역)** 이다.
#
# 스펙 §2.2: "화면은 (근무지역) 축으로 통일한다. 그래야 구인과 구직이 같은
# 잣대가 된다." 그런데 이 두 함수는 (지역별)시도(사업장 소재지)를 읽고 있었다.
# 실측이 그 차이를 숫자로 보여준다 — 2026년 07월 서울:
#     (지역별)시도    유효구인 29,196 / 유효구직 268,616
#     (근무지역)시도  유효구인 15,125 / 유효구직 355,893
# 그래서 총괄 화면의 서울과 직종별 화면의 서울(= (근무지역)시군구 합)이 같은
# 앱 안에서 서로 다른 정의가 됐다. 시도 축을 (근무지역)으로 옮겨 통일한다.
#
# **피보험자는 예외다** — (사업장) 축이 유일한 축이라 collect_insured_sido 는
# 그대로 두고, 화면도 이미 "사업장 소재지 기준"이라고 밝히고 있다.
# ---------------------------------------------------------------------------

def collect_vacancy_sido(rows) -> list[dict]:
    """(근무지역)시도(또는 총계) 축 유효구인구직 행 — 시군구 합산 금지 규칙(R4)의 짝."""
    out = []
    for row in rows:
        out.append({
            "period": period_code(row["마감년월"]),
            "sido": sido_code(_axis(row, "(근무지역)시도")),
            "vacancy": to_number(row.get("유효구인인원(전체)")),
            "seekers": to_number(_first(row, _SEEKERS_KEYS)),
        })
    return out


def collect_placement_sido(rows) -> list[dict]:
    """(근무지역)시도 축 취업건수 행 (R45)."""
    out = []
    for row in rows:
        out.append({
            "period": period_code(row["마감년월"]),
            "sido": sido_code(_axis(row, "(근무지역)시도")),
            "placements": to_number(row.get("취업건수(월)")),
        })
    return out


def collect_insured_sido(rows) -> list[dict]:
    """(사업장)시도 축 피보험자 행 — R45 의 명시적 예외((사업장)이 유일한 축이다)."""
    out = []
    for row in rows:
        out.append({
            "period": period_code(row["마감년월"]),
            "sido": sido_code(_axis(row, "(사업장)시도")),
            "insured": to_number(row.get("피보험자수(전체)")),
            "gained": to_number(row.get("취득자수(월)")),
            "lost": to_number(row.get("상실자수(월)")),
        })
    return out
