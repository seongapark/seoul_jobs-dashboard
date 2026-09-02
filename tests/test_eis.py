"""pipeline.eis 테스트 — 순수 함수 수집기, 네트워크 없음.

브리프(task-7-brief.md)가 준 5개 테스트를 그대로 담고, 컨트롤러 룰링(R2b/R4)과
Task 7 Step 0 탐침에서 드러난 실측 사실(측정값 컬럼명이 브리프 가정과 다름,
시군구 코드 70개 로딩)을 검증하는 테스트를 더한다.
"""
import json
from pathlib import Path

import pytest

from pipeline import eis, center_map

ROOT = Path(__file__).resolve().parents[1]
CM = center_map.load(ROOT / "data/center_map.json")
VACANCY_FIXTURE = ROOT / "tests/fixtures/eis_vacancy_rows.json"
INSURED_FIXTURE = ROOT / "tests/fixtures/eis_insured_rows.json"


# ---------------------------------------------------------------------------
# 브리프 Step 1 — 그대로
# ---------------------------------------------------------------------------

def test_vacancy_rows_get_center_attached():
    rows = [{"마감년월": "2026년 07월", "(근무지역)시군구": "서울특별시 강남구",
             "직종_중분류": "2025직종_경영·행정·사무직", "산업_대분류": "J 정보통신업",
             "유효구인인원(전체)": "742", "유효구직건수(전체)": "1,980"}]
    out = eis.collect_vacancy(rows, CM)
    assert out[0]["center"] == "서울강남고용센터"
    assert out[0]["sigungu"] == "11680"
    assert out[0]["period"] == "202607"
    assert out[0]["vacancy"] == 742
    assert out[0]["seekers"] == 1980


def test_unknown_sigungu_is_rejected_loudly():
    """모르는 지역을 조용히 버리면 합계가 어긋난 채 배포된다."""
    rows = [{"마감년월": "2026년 07월", "(근무지역)시군구": "경상남도 통영시",
             "직종_중분류": "x", "산업_대분류": "y",
             "유효구인인원(전체)": "1", "유효구직건수(전체)": "1"}]
    with pytest.raises(eis.UnknownRegion):
        eis.collect_vacancy(rows, CM)


def test_gyeonggi_general_district_row_is_rejected():
    rows = [{"마감년월": "2026년 07월", "(근무지역)시군구": "경기도 수원시 장안구",
             "직종_중분류": "x", "산업_대분류": "y",
             "유효구인인원(전체)": "1", "유효구직건수(전체)": "1"}]
    with pytest.raises(eis.UnknownRegion):
        eis.collect_vacancy(rows, CM)


def test_insured_computes_net_change():
    rows = [{"마감년월": "2026년 07월", "(사업장)시군구": "서울특별시 강남구",
             "직종_중분류": "2025직종_경영·행정·사무직", "산업_대분류": "J 정보통신업",
             "피보험자수(전체)": "712,480", "취득자수(월)": "21,940", "상실자수(월)": "23,180"}]
    out = eis.collect_insured(rows, CM)
    assert out[0]["insured"] == 712480
    assert out[0]["gained"] - out[0]["lost"] == -1240


def test_mobility_keeps_previous_industry():
    rows = [{"마감년월": "2026년 07월", "(사업장)시도": "서울",
             "산업_대분류": "J 정보통신업", "산업(이전)_대분류": "M 전문, 과학 및 기술 서비스업",
             "경력이동자수(월)": "1,280"}]
    out = eis.collect_mobility(rows)
    assert out[0]["prev_industry"].startswith("M")
    assert out[0]["movers"] == 1280


def test_mobility_sido_is_the_administrative_standard_code():
    """collect_vacancy_sido 등과 같이, collect_mobility 도 이름("서울")이 아니라
    행정표준코드("11")를 내야 est.py 와 join 이 된다 — 여기만 이름 그대로
    두면 수도권 세 시도 값이 필터 없이 섞인다(R35)."""
    rows = [{"마감년월": "2026년 07월", "(사업장)시도": "서울",
             "산업_대분류": "J 정보통신업", "산업(이전)_대분류": "M 전문, 과학 및 기술 서비스업",
             "경력이동자수(월)": "1,280"}]
    out = eis.collect_mobility(rows)
    assert out[0]["sido"] == "11"


def test_mobility_rejects_sido_outside_the_metro_area():
    """다른 sido 수집기와 마찬가지로, 수도권 밖 시도를 조용히 넘기면 안 된다."""
    rows = [{"마감년월": "2026년 07월", "(사업장)시도": "부산",
             "산업_대분류": "J 정보통신업", "산업(이전)_대분류": "M 전문, 과학 및 기술 서비스업",
             "경력이동자수(월)": "1"}]
    with pytest.raises(eis.UnknownRegion):
        eis.collect_mobility(rows)


# ---------------------------------------------------------------------------
# R40 — normalize_name(): est(KOSIS)와 eis 두 출처의 이름 표기를 맞춘다.
#
# 컨트롤러가 KOSIS 를 직접 불러 확인(2026-09-02)한 실측 문자열을 그대로 쓴다 —
# 코드포인트가 진짜여야 의미가 있다. KOSIS 는 코드 접두 + 한글 아래아(ㆍ,
# U+318D) 를 쓰고, EIS 는 접두 없이 가운뎃점(·, U+00B7) 을 쓴다.
# ---------------------------------------------------------------------------

def test_normalize_name_unifies_kosis_and_eis_separators_and_strips_code_prefix():
    kosis_name = "02 경영ㆍ행정ㆍ사무직"          # 실측: DT_118N_DEN062, C3_NM
    eis_name = "경영·행정·사무직"                 # 실측: eis_insured_rows.json (_strip_prefix 통과 후)
    assert eis.normalize_name(kosis_name) == eis.normalize_name(eis_name) == "경영·행정·사무직"


def test_normalize_name_keeps_parenthetical_detail_intact():
    text = "82 금속ㆍ재료 설치ㆍ정비ㆍ생산직 (판금ㆍ단조ㆍ주조ㆍ용접ㆍ도장 등)"
    assert eis.normalize_name(text) == "금속·재료 설치·정비·생산직 (판금·단조·주조·용접·도장 등)"


def test_normalize_name_leaves_names_without_a_numeric_code_prefix_alone():
    """"전직종"처럼 코드 접두가 없는 이름에서 숫자 아닌 부분을 잘라내면 안 된다."""
    assert eis.normalize_name("전직종") == "전직종"


def test_normalize_name_handles_single_digit_major_category_code():
    assert eis.normalize_name("9 농림어업직") == "농림어업직"


# ---------------------------------------------------------------------------
# R2b — SIGUNGU_NAME_TO_CODE 는 임포트 시 한 번만 만들어진다
# ---------------------------------------------------------------------------

def test_sigungu_name_to_code_has_70_entries_at_import_time():
    assert len(eis.SIGUNGU_NAME_TO_CODE) == 70
    assert eis.SIGUNGU_NAME_TO_CODE["서울특별시 강남구"] == "11680"
    assert eis.SIGUNGU_NAME_TO_CODE["경기도 화성시"] == "41590"
    assert eis.SIGUNGU_NAME_TO_CODE["경기도 가평군"] == "41820"  # 강원지청 관할이지만 이름표는 경기도


def test_gyeonggi_general_districts_are_not_in_the_name_map():
    """수원시 4개 일반구 이름이 들어있으면 시군구 코드와 함께 이중계상된다."""
    for banned_name in ("경기도 수원시 장안구", "경기도 수원시 권선구",
                        "경기도 수원시 팔달구", "경기도 수원시 영통구"):
        assert banned_name not in eis.SIGUNGU_NAME_TO_CODE


# ---------------------------------------------------------------------------
# 실측 교정 — 실제 OLAP 헤더는 "유효구직자수(전체)" 다 (브리프 가정과 다르다).
# tests/fixtures/olap_grid.json (Task 6, 실뷰어 캡처) 이 증거다.
# ---------------------------------------------------------------------------

def test_collect_vacancy_reads_the_real_olap_header_name_too():
    """브리프는 "유효구직건수(전체)" 를 가정했지만 실제 뷰어 헤더는
    "유효구직자수(전체)" 다 (tests/fixtures/olap_grid.json 참고). 둘 중 있는
    쪽을 읽어야 실데이터에서 seekers 가 조용히 0 이 되지 않는다."""
    rows = [{"마감년월": "2026년 07월", "(근무지역)시군구": "서울특별시 강남구",
             "직종_중분류": "x", "산업_대분류": "y",
             "유효구인인원(전체)": "25", "유효구직자수(전체)": "711"}]
    out = eis.collect_vacancy(rows, CM)
    assert out[0]["seekers"] == 711


# ---------------------------------------------------------------------------
# 실측 fixture — Task 7 Step 0 탐침 (tools/probe_dragdrop3.py, 2026-09-01)에서
# 실제 뷰어에 (근무지역)시군구 × 직종_중분류 레이아웃을 만들어 읽은 값
# (2026년 07월, 2025직종_관리직(임원·부서장), 서울 23개구 페이지 1분).
# ---------------------------------------------------------------------------

def test_collect_vacancy_over_real_captured_grid_sample():
    rows = json.loads(VACANCY_FIXTURE.read_text(encoding="utf-8"))
    out = eis.collect_vacancy(rows, CM)

    assert len(out) == 23
    assert all(r["period"] == "202607" for r in out)
    assert all(r["occupation"] == "관리직(임원·부서장)" for r in out)
    # 시군구 코드가 다 매핑됐다 — UnknownRegion 없이 여기까지 왔다는 것 자체가 증거
    assert {r["sigungu"] for r in out} <= CM.codes()
    assert all(r["center"] == "서울강남고용센터" for r in out
               if r["sigungu"] == "11680")

    assert sum(r["vacancy"] for r in out) == 153
    assert sum(r["seekers"] for r in out) == 3353


# ---------------------------------------------------------------------------
# R4 — 시도 단위는 시군구 합으로 만들지 않는다. 시도 그리드를 따로 읽는다.
#
# 검증값은 **(근무지역)시도 축을 직접 실측한 값**이다 (2026-09-02,
# tools/probe_fetchers.py 계열 탐침, 2026년 07월). R45 로 이 축이 (지역별)에서
# (근무지역)으로 바뀌면서 값도 함께 바뀌었다 — 이 앵커에 옛 (지역별) 값을
# 남겨두면 새 컬럼 이름 아래 **그 축이 낼 수 없는 값**을 단언하게 되고, 나중에
# 누가 이걸로 대조하면 틀린 축의 출력을 "검증"하게 된다(리뷰 Important 3).
#
#   축            서울             경기             인천
#   (지역별)      29,196/268,616   45,743/407,355   7,501/99,637   <- 옛 앵커, 지금은 틀림
#   (근무지역)    15,125/355,893   48,938/317,754   9,268/86,627   <- 실측, 지금 쓰는 값
#
# 전국 총계(165,821/1,550,154)는 두 축에서 같다 — 축은 분해 방식만 바꾼다.
# ---------------------------------------------------------------------------

def test_collect_vacancy_sido_matches_measured_working_area_totals():
    rows = [
        {"마감년월": "2026년 07월", "(근무지역)시도": "총계",
         "유효구인인원(전체)": "165,821", "유효구직자수(전체)": "1,550,154"},
        {"마감년월": "2026년 07월", "(근무지역)시도": "서울",
         "유효구인인원(전체)": "15,125", "유효구직자수(전체)": "355,893"},
        {"마감년월": "2026년 07월", "(근무지역)시도": "경기",
         "유효구인인원(전체)": "48,938", "유효구직자수(전체)": "317,754"},
        {"마감년월": "2026년 07월", "(근무지역)시도": "인천",
         "유효구인인원(전체)": "9,268", "유효구직자수(전체)": "86,627"},
    ]
    out = eis.collect_vacancy_sido(rows)
    by_sido = {r["sido"]: r for r in out}

    assert by_sido["00"] == {"period": "202607", "sido": "00", "vacancy": 165821, "seekers": 1550154}
    assert by_sido["11"]["vacancy"] == 15125 and by_sido["11"]["seekers"] == 355893
    assert by_sido["41"]["vacancy"] == 48938 and by_sido["41"]["seekers"] == 317754
    assert by_sido["28"]["vacancy"] == 9268 and by_sido["28"]["seekers"] == 86627


def test_collect_vacancy_sido_rows_have_no_sigungu_or_center_field():
    """R4: 시도 단위 행은 sigungu/center 를 안 갖는다 — 시군구 코드 체계와
    섞이면 "시도값을 시군구 합으로 만든 것"처럼 잘못 읽힐 위험이 있다."""
    rows = [{"마감년월": "2026년 07월", "(근무지역)시도": "서울",
             "유효구인인원(전체)": "1", "유효구직자수(전체)": "1"}]
    out = eis.collect_vacancy_sido(rows)
    assert "sigungu" not in out[0]
    assert "center" not in out[0]


def test_collect_insured_sido_and_placement_sido_read_sido_axis():
    insured_rows = [{"마감년월": "2026년 07월", "(사업장)시도": "서울",
                      "피보험자수(전체)": "4,698,520", "취득자수(월)": "193,339",
                      "상실자수(월)": "192,131"}]
    out = eis.collect_insured_sido(insured_rows)
    assert out[0] == {"period": "202607", "sido": "11",
                       "insured": 4698520, "gained": 193339, "lost": 192131}

    placement_rows = [{"마감년월": "2026년 07월", "(근무지역)시도": "경기",
                        "취업건수(월)": "12,345"}]
    out = eis.collect_placement_sido(placement_rows)
    assert out[0] == {"period": "202607", "sido": "41", "placements": 12345}


def test_sido_collectors_reject_unmapped_sido_names():
    """수도권 밖 시도가 섞여 들어오면 조용히 버리지 않고 시끄럽게 실패한다."""
    rows = [{"마감년월": "2026년 07월", "(근무지역)시도": "부산",
             "유효구인인원(전체)": "1", "유효구직자수(전체)": "1"}]
    with pytest.raises(eis.UnknownRegion):
        eis.collect_vacancy_sido(rows)


# ---------------------------------------------------------------------------
# collect_placement — 브리프 Step 3 예시에 있었지만 Step 1 테스트엔 없던 함수.
# 최소 계약 하나는 지킨다.
# ---------------------------------------------------------------------------

def test_collect_placement_attaches_center():
    rows = [{"마감년월": "2026년 07월", "(근무지역)시군구": "경기도 화성시",
             "직종_중분류": "2025직종_기계·금속·재료 관련직",
             "취업건수(월)": "1,204"}]
    out = eis.collect_placement(rows, CM)
    assert out[0]["center"] == "화성고용센터"
    assert out[0]["placements"] == 1204


# ---------------------------------------------------------------------------
# 피보험자 fixture — 구조 검증용 표본 (실뷰어 미캡처, fixture 파일의 _source 참고).
# ---------------------------------------------------------------------------

def test_collect_insured_over_structural_sample_fixture():
    payload = json.loads(INSURED_FIXTURE.read_text(encoding="utf-8"))
    assert "실뷰어" in payload["_source"] or "표본" in payload["_source"]  # 출처 경고가 살아있는지
    out = eis.collect_insured(payload["rows"], CM)
    assert len(out) == 4
    assert all(r["sigungu"] in CM.codes() for r in out)
    assert {r["center"] for r in out} == {
        "서울강남고용센터", "서울고용센터", "화성고용센터", "인천고용센터",
    }


# ---------------------------------------------------------------------------
# R45 — 시도 축은 (근무지역)이다. 옛 축을 조용히 받아들이지 않는다.
# ---------------------------------------------------------------------------

def test_vacancy_sido_rejects_the_old_regional_axis_column():
    """옛 컬럼((지역별)시도)을 대체 이름으로 받아주면 '틀린 축을 조용히 통과'시킨다.

    실측(2026-09-02) 2026년 07월 서울: (지역별) 29,196 vs (근무지역) 15,125 —
    조용히 통과시키면 총괄 화면과 직종별 화면의 '서울'이 서로 다른 정의가 된다."""
    rows = [{"마감년월": "2026년 07월", "(지역별)시도": "서울",
             "유효구인인원(전체)": "29,196", "유효구직자수(전체)": "268,616"}]
    with pytest.raises(eis.WrongAxis):
        eis.collect_vacancy_sido(rows)


def test_placement_sido_rejects_the_old_regional_axis_column():
    rows = [{"마감년월": "2026년 07월", "(지역별)시도": "경기", "취업건수(월)": "1,000"}]
    with pytest.raises(eis.WrongAxis):
        eis.collect_placement_sido(rows)


def test_insured_sido_keeps_the_workplace_axis():
    """피보험자는 R45 의 명시적 예외 — (사업장)이 유일한 축이라 그대로 둔다."""
    rows = [{"마감년월": "2026년 07월", "(사업장)시도": "서울",
             "피보험자수(전체)": "10", "취득자수(월)": "1", "상실자수(월)": "2"}]
    assert eis.collect_insured_sido(rows)[0]["sido"] == "11"

    with pytest.raises(eis.WrongAxis):
        eis.collect_insured_sido([{"마감년월": "2026년 07월", "(근무지역)시도": "서울",
                                   "피보험자수(전체)": "10"}])
