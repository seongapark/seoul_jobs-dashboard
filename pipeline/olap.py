"""렌더된 EIS OLAP 뷰어 그리드를 읽어 행 리스트로 편다.

경로 확정 (tools/probe_olap.py 로 탐침, 2026-09-01):
  cube/queries.do 의 POST 페이로드 안 "sql" 필드는 AES 로 암호화된 문자열이다
  (crypto-js.min.js + WISE.widget.CrpytoAES256.js 로 세션 키 암복호화). 감싸는
  JSON 봉투는 평문이지만 실데이터는 없고, 실제 그리드는 DevExtreme PivotGrid
  (dx-pivotgrid — 브리프가 가정한 dx-datagrid 가 아니다) 로 클라이언트 렌더링된다.
  따라서 이 모듈은 **DOM 추출** 경로를 쓴다: 렌더된 표를 읽는다.

  보고서 "유효구인구직" (17개 시도 + 총계 = 18행) 은 헤드리스에서도 스크롤 없이
  전량이 DOM 에 이미 존재했다 (dataScroll=Y 는 더 큰 표, 예: 시군구 단위에 대비한
  것으로 보인다). 안전을 위해 fetch_grid 는 그래도 스크롤-누적을 시도한다.

Task 7 Step 0 탐침 추가 (2026-09-01, tools/probe_flat_sigungu.py 등):
  위 가정은 절반만 맞았다. dataScroll=Y 무한 스크롤은 행이 적어 원래 스크롤이
  필요 없던 표(시도 17행)에서만 확인됐을 뿐, 실제로 행이 많은 표는 스크롤이
  아니라 **DevExtreme 데이터그리드 스타일 페이저**(`.dx-datagrid-pager`,
  `.dx-pages` 안에 `.dx-page` 들)로 나뉘어 렌더된다. (지역별)시군구 단독(중첩
  없이, ~250행)만 놓아도 페이지 6개로 쪼개져 최초 로드에는 50행만 DOM 에 있다.
  이 상태에서 `.dx-pivotgrid-area-data .dx-scrollable-container` 를 스크롤해도
  더 이상 새 행이 나오지 않으므로 (같은 페이지 안에서 스크롤이 끝까지 갔을 뿐,
  다음 페이지로 안 넘어간다) 루프는 "안정화됐다"고 착각하고 50행짜리 그리드를
  아무 예외 없이 반환한다 — 이 모듈이 막으려던 바로 그 "잘렸는데 그럴듯한 결과"
  다. 그래서 스크롤을 시도하기 전에 페이저 존재를 먼저 확인해 시끄럽게 실패
  시킨다(`OlapPaginationError`). 페이지네이션을 실제로 넘겨가며 누적하는 로직은
  아직 없다 — 후속 작업.

Task 7b (2026-09-01): 그 후속 작업 — 페이지네이션 누적을 구현했다. 페이저가
  2개 이상이면 더 이상 즉시 실패하지 않는다. 대신 1페이지째는 이미 읽어둔 채로
  `.dx-datagrid-pager .dx-page` 버튼을 2페이지부터 순서대로 클릭해 걷는다
  (`_walk_paginated_grid`). 실패는 여전히 시끄럽다 — 페이지 클릭이 행을 못
  바꾸면, 어느 페이지가 새 행을 하나도 못 보태면, 어느 페이지가 데이터 행을
  하나도 안 주면(`OlapExtractionError`), 마지막이 아닌 페이지가 `_PAGE_SIZE`
  와 다르면, 또는 페이지를 넘나들며 반복된 행이 알려진 요약 라벨이 아니면
  (R14, 아래 Fix round 3 참고) 모두 `OlapPageWalkError` 를 낸다. 잘린 그리드를
  반환하는 대신 예외를 낸다는 원칙은 그대로다.

Task 7b Fix round 1 (2026-09-01, 컨트롤러 R12): 처음엔 "원시 합계 == 고유 행
  수"라는 엄격한 동등성으로 완전성을 검증했는데, 라이브 사이트 실측(6페이지,
  원시 267행 vs 고유 262행)이 이 체크가 실데이터에서 절대 통과 못 함을
  보였다. 그때는 원인을 "그룹이 페이지 경계에 걸치면 DevExtreme PivotGrid 가
  그 그룹의 헤더 행을 다음 페이지 맨 위에 다시 그린다"고 추정해 동등성 대신
  "중복 <= 경계 수(pager_count-1)" 상한으로 바꿨다 — 이 추정은 **틀렸다**
  (아래 Fix round 2 참고).

Task 7b Fix round 2 (2026-09-02, tools/probe_pagination_dedup_evidence.py):
  리터럴 행 텍스트로 실측했더니 5개 중복은 서로 다른 5개 그룹 헤더가 아니라
  **같은 한 행**이 6페이지 전부(1페이지 포함, 경계와 무관)에 반복된 것이었다:
  `['총계', '165,821', '1,550,154']`. 즉 그룹 헤더가 페이지 경계에 걸쳐
  다시 그려지는 게 아니라, 그랜드토탈(총계) 행이 매 페이지 맨 위에
  **고정(pinned)** 되어 렌더된다. "중복 <= 경계 수" 상한은 이 사례에서
  숫자상 우연히(5=5) 통과했을 뿐이다 — 시군구 데이터 행 두 개가 우연히 값이
  같아 중복으로 잡혔어도 똑같이 통과시켰을 것이므로, 개수 기반 상한 자체가
  원리적으로 근거가 없었다.

Task 7b Fix round 3 (2026-09-02, 컨트롤러 R13/R14): 그래서 개수 기반 상한을
  버리고 **정체성 기반** 규칙으로 바꿨다 — 중복된 행은 그 첫 칸이 알려진
  요약 라벨(`_SUMMARY_ROW_LABELS`)일 때만 허용한다. 모르는 라벨이
  반복되면(=그리드 구조를 이해하지 못했다는 뜻) 개수와 무관하게 시끄럽게
  실패한다(R14). 그리고 이 프로젝트의 데이터 계약("유효구직건수의 분해값을
  더해 총계로 쓰지 않는다 — 총계는 총계 행에서 받는다")을 실제로 지킬 수
  있도록, 허용된 요약 행은 본문에서 빼 별도로 돌려준다(R13) — 조용히 버리지
  않는다.

Task 7b Fix round 4 (2026-09-02, 컨트롤러 R15/R16 — 리뷰 루프): 두 가지를
  더 고쳤다.
  1. (R15) Fix round 3 의 반환 타입 `_WithSummaries(list)` 는 list 를
     상속해 `.summaries` 속성을 얹는 방식이었는데, 이 패턴은 슬라이싱·
     `list(...)`·`+`·컴프리헨션 등 어떤 list 연산을 거치기만 해도
     `.summaries` 가 조용히 사라진다 — 특히 자연스러운 다음 소비 패턴인
     `parse_grid(fetch_grid(...))` 는 `list[dict]` 를 돌려주는데 총계가
     아무 예외 없이 그냥 없어진다. R13 이 막으려던 바로 그 조용한 손실을
     되살리는 결함이었다. `Grid(header, rows, summaries)` 라는 명시적
     타입(typing.NamedTuple)으로 바꿨다 — 필드 3개짜리 튜플이라 옛
     `header, *body = grid` 언패킹(대상 2개 + 별표 1개)은 문법상은 계속
     되지만, `body` 가 이제 `[grid.rows, grid.summaries]`(리스트 두 개짜리)
     로 완전히 뒤바뀐다 — `header` 는 우연히 값이 맞아 조용해 보여도, `body`
     를 실제로 쓰는 다음 줄(행을 순회하거나 `"".join(row)` 를 하는 등)에서
     빠르게 `TypeError`/`AssertionError` 로 깨진다. 조용히 총계가 사라지는
     쪽보다 이렇게 시끄럽게 깨져 호출부를 강제로 고치게 만드는 쪽이 낫다는
     판단이다. 저장소 안 모든 호출부(테스트, `fetch_and_parse_grid`,
     `tools/probe_pagination_walk.py`)를 `grid.header`/`grid.rows`/
     `grid.summaries` 로 갱신했다.
  2. (R16) `_SUMMARY_ROW_LABELS` 를 실측으로 확인된 `{"총계"}` 하나로
     줄였다. 소계/합계/전체는 확인된 적이 없고, 특히 "전체"는 실제 지역/
     범주 값으로도 그럴듯해 요약 행으로 잘못 분류하면 데이터 행 하나가
     조용히 본문에서 빠질 위험이 있었다 — 코드는 화이트리스트라고 주장하면서
     주석은 "확인 전엔 추가하지 않는다"고 말하는 자기모순이기도 했다. 다른
     보고서에서 실제로 소계가 고정 반복되는 게 확인되면, 그때는 이 목록에
     추가하기 전에 먼저 예외로 시끄럽게 실패한다 — 그게 설계 의도다.
"""
from __future__ import annotations

from typing import NamedTuple

# 실측: EIS 데이터그리드 페이저의 페이지당 행 수 (tools/probe_flat_sigungu.py,
# (지역별)시군구 단독 축 ~250행 → 페이지 6개 x 50행/페이지).
_PAGE_SIZE = 50
_PAGER_CONTAINER_SELECTOR = ".dx-datagrid-pager"
_PAGER_SELECTOR = f"{_PAGER_CONTAINER_SELECTOR} .dx-page"
# 지금 보고 있는 페이지에는 `dx-selection` 이 붙는다 (실측 2026-09-03: '다음' 을
# 누르면 선택이 새 창의 첫 번호로 함께 옮겨간다). 이걸 봐야 "클릭이 안 먹었다"와
# "먹었는데 렌더가 느리다"를 가를 수 있다.
_PAGER_SELECTED_SELECTOR = f"{_PAGER_SELECTOR}.dx-selection"
# 페이저가 진짜 있으면 보통 이 안에 뜬다. 없으면 이 시간을 다 기다린 뒤에야
# "없다"고 판단한다 — 고정 500ms 대기보다 느릴 수 있지만, 늦게 뜨는 페이저를
# "없다"고 오판해 조용히 첫 페이지만 반환하는 쪽보다 안전 쪽으로 실패한다.
_PAGER_WAIT_MS = 5_000


class OlapExtractionError(RuntimeError):
    """그리드 추출이 불완전하거나 비어 있을 때 낸다.

    이 파이프라인의 원칙: 잘린 그리드를 그럴듯하게 반환하지 않는다. 완전한지
    확신이 없으면 조용히 절반만 반환하는 대신 시끄럽게 실패한다.
    """


class OlapPaginationError(OlapExtractionError):
    """그리드가 스크롤이 아니라 (다중) 페이지로 나뉘어 있을 때 낸다.

    fetch_grid 의 스크롤-누적 루프는 페이지네이션을 넘기지 못한다 — 같은 페이지
    안에서 스크롤이 끝까지 가면 "더 안 늘어난다"며 안정화된 것으로 착각해 첫
    페이지만 조용히 반환한다. 페이지가 2개 이상이면 스크롤을 시도하기도 전에
    이 예외를 낸다. 페이지네이션 누적은 아직 구현되지 않았다.
    """


class OlapPageWalkError(OlapPaginationError):
    """다중 페이지 그리드를 누적하는 도중 무언가 신뢰할 수 없을 때 낸다 (Task 7b).

    다음 중 하나면 이 예외를 낸다 — 모두 "잘렸을 수 있는데 그럴듯한 결과"를
    막기 위함이다:
      - 페이지 버튼을 클릭해 다음 페이지로 이동을 시도했는데 렌더된 행이 이전
        페이지와 똑같다 (클릭이 페이지를 못 넘겼을 가능성).
      - 어느 페이지가 새 행을 하나도 보태지 못했다 (순서만 바뀌었거나 다른
        페이지와 겹쳤을 가능성 — 위 항목보다 일반적인 체크).
      - 마지막 페이지가 아닌 페이지가 본문 행 수 `_PAGE_SIZE` 와 다르다.
      - 페이지를 넘나들며 반복된 행이 있는데, 그 첫 칸이 알려진 요약 행 라벨
        (`_SUMMARY_ROW_LABELS` — 실측으로 확인된 `"총계"` 하나뿐, R16)이
        아니다 (R14). 실측(2026-09-02,
        tools/probe_pagination_dedup_evidence.py)으로 확인된 진짜 원인은
        "그룹 헤더가 페이지 경계에 걸쳐 다시 그려진다"가 아니라,
        **그랜드토탈(총계) 행이 매 페이지 맨 위에 고정(pinned)되어 반복
        렌더된다**는 것이었다 — 알려진 요약 라벨의 반복은 정상으로 보고
        통과시키되 본문에서 빼 `Grid.summaries` 로 돌려주고(R13), 모르는
        라벨의 반복은 원인 불명의 손실/중복으로 보고 그 행과 등장 페이지를
        그대로 이름 붙여 예외를 낸다.
    """


# 페이지 이동 사이 짧은 대기 (정중함) — 스크롤 폴링 대기(200ms)와 같은 자릿수.
_PAGE_ADVANCE_WAIT_MS = 400

# R47 실측(2026-09-02) — 무거운 그리드(시군구 × 직종)는 페이지 버튼을 눌러도
# **0.4초 뒤에는 이전 페이지가 그대로 남아 있고 3.4초쯤에야 갱신된다.** 고정
# 400ms 대기 뒤에 읽으면 이전 페이지를 새 페이지로 착각한다 — 실제로 그래서
# 12페이지에서 "렌더된 행이 이전 페이지와 똑같다"로 죽었다. 시간에 기대는
# 대신 **본문이 실제로 바뀔 때까지 폴링**한다. 끝내 안 바뀌면 호출부가 예외를
# 낸다(그 판정은 그대로 둔다 — 조용히 같은 페이지를 두 번 담지 않는다).
_PAGE_RENDER_POLL_MS = 400
_PAGE_RENDER_MAX_POLLS = 75      # 최대 30초
# 200페이지짜리 걷기에서는 클릭 하나가 이따금 먹지 않는다(실측: 151페이지까지
# 잘 가다가 152페이지에서 렌더가 안 바뀜). 한 번은 다시 눌러 본다 — 그래도
# 안 바뀌면 예외다. "여러 번 누르다 보면 되겠지"가 아니라 **딱 한 번 더**이고,
# 실패는 여전히 시끄럽다.
_PAGE_CLICK_ATTEMPTS = 2

# 페이지를 넘기면 로딩 오버레이가 뜨고, 그동안 페이저 클릭은 가로채인다
# (`progress_back_panel ... intercepts pointer events`). 실측(2026-09-03):
# `#progress_box` 는 늘 DOM 에 있고 `display:none` 으로 토글되며, 정상이면
# 0.4~0.5초면 걷힌다. EIS 가 느려지면 30초를 넘겨 Playwright 의 클릭 재시도가
# 먼저 타임아웃한다 — 다섯 번째 실측 수집이 42분을 걷고도 그렇게 죽었다.
# 그래서 클릭 재시도에 기대는 대신 **걷힐 때까지 기다린 뒤** 누른다
# (layout._requery 가 '작업 취소' 스피너를 기다리는 것과 같은 방식).
_OVERLAY_SELECTOR = "#progress_box"
_OVERLAY_MAX_POLLS = 150         # 최대 60초

# ---------------------------------------------------------------------------
# R47 (Task 15a 실측, 2026-09-02) — 페이저는 "전체 페이지 목록"이 아니라 **창**이다.
#
# 관측한 페이저 텍스트: '12345678910다음'. 숫자 버튼은 최대 10개까지만 보이고,
# 그보다 페이지가 많으면 끝에 "다음" 버튼이 붙는다. `.dx-page` 는 그 "다음"까지
# 세므로 `.dx-page` 개수(=11)를 전체 페이지 수로 믿으면 **예외 없이 잘린
# 그리드**가 나간다(실측: 시군구 70개 중 14개만 수집하고 성공한 척했다).
# 그래서 이제 창을 넘겨가며 끝까지 걷는다.
# ---------------------------------------------------------------------------
_PAGER_NEXT_LABEL = "다음"
# 걷는 데 직접 쓰지는 않지만 "모르는 버튼"과 구별해야 하는 이동 버튼들.
# "다음"만 실측으로 확인했고 나머지는 창 2 이후에 나타날 법한 이름이다 —
# 모르는 버튼이 나오면 아래 `_check_pager_labels` 가 시끄럽게 실패한다.
_PAGER_NAV_LABELS = frozenset({_PAGER_NEXT_LABEL, "이전", "처음", "마지막"})
# 무한 루프 방지 상한. 실측 최대 워크로드(시군구 289 × 직종 36 ÷ 50행 ≈ 210페이지)
# 보다 넉넉하다. 여기 닿으면 조용히 멈추지 않고 예외를 낸다.
_MAX_PAGES = 1_000


def _pager_labels(page) -> list[str]:
    """페이저 버튼의 라벨을 DOM 순서 그대로 읽는다 (숫자들 + "다음" 등)."""
    return [text.strip() for text in
            page.eval_on_selector_all(_PAGER_SELECTOR, "els => els.map(e => e.innerText)")]


def _check_pager_labels(labels) -> None:
    """숫자도 아니고 알려진 이동 버튼도 아닌 라벨이 있으면 실패한다.

    페이저 구조를 이해하지 못한 채 걸으면 잘린 그리드가 조용히 나간다 —
    이 모듈의 원칙대로 그러느니 시끄럽게 실패한다.
    """
    unknown = [text for text in labels
               if not text.isdigit() and text not in _PAGER_NAV_LABELS]
    if unknown:
        raise OlapPaginationError(
            f"페이저에 모르는 버튼({unknown})이 있다 — 페이저 구조가 바뀌었을 수 있다. "
            f"아는 것은 숫자 버튼과 {sorted(_PAGER_NAV_LABELS)} 뿐이다.")


def _overlay_visible(page) -> bool:
    """로딩 오버레이가 화면을 덮고 있는가.

    실측(2026-09-03): `#progress_box` 는 **늘 DOM 에 있고** `display:none` 으로
    토글된다 — 그래서 존재가 아니라 **가시성**을 본다(layout.py 의 '작업 취소'
    스피너와 같은 함정이다: 존재로 판단하면 영원히 "떠 있다"가 된다).
    """
    locator = page.locator(_OVERLAY_SELECTOR)
    return locator.count() > 0 and locator.first.is_visible()


def _wait_out_overlay(page) -> None:
    for _ in range(_OVERLAY_MAX_POLLS):
        if not _overlay_visible(page):
            return
        page.wait_for_timeout(_PAGE_RENDER_POLL_MS)
    raise OlapPageWalkError(
        f"로딩 오버레이({_OVERLAY_SELECTOR})가 "
        f"{_OVERLAY_MAX_POLLS * _PAGE_RENDER_POLL_MS // 1000}초 안에 안 걷힌다 — "
        "클릭이 가로채이므로 잘렸을 수 있는 그리드를 반환하지 않는다.")


def _click_pager_label(page, label: str) -> None:
    _wait_out_overlay(page)
    labels = _pager_labels(page)
    try:
        index = labels.index(label)
    except ValueError:
        raise OlapPageWalkError(
            f"페이저에서 '{label}' 버튼을 못 찾는다 (현재 버튼: {labels})") from None
    page.locator(_PAGER_SELECTOR).nth(index).click()
    page.wait_for_timeout(_PAGE_ADVANCE_WAIT_MS)


def _labels_after_window_move(page, before: list[str]) -> list[str]:
    """"다음"을 누른 뒤 페이저 라벨이 실제로 바뀔 때까지 기다렸다가 돌려준다.

    본문 렌더가 늦는 것(_body_after_render)과 같은 이유로 라벨도 늦을 수 있다.
    고정 대기 뒤에 읽으면 옛 창을 그대로 보고 "더 큰 번호가 없다 = 끝"이라고
    **조용히 오판**한다 — 잘린 그리드가 예외 없이 나가는, 이 모듈이 가장
    막고 싶은 실패다. 끝내 안 바뀌면 옛 라벨을 돌려주고, 진짜 끝인지 아닌지는
    걷기가 끝난 뒤 `_check_walk_completeness` 가 페이지 크기로 교차검증한다.
    """
    labels = before
    for _ in range(_PAGE_RENDER_MAX_POLLS):
        labels = _pager_labels(page)
        if labels != before:
            return labels
        page.wait_for_timeout(_PAGE_RENDER_POLL_MS)
    return labels


def _check_walk_completeness(page, visited: int, page_count: int) -> None:
    """걷기를 멈춘 지점이 정말 마지막 페이지인지 **페이저에게 직접 묻는다.**

    실측(2026-09-02)이 확인한 권위 있는 종료 신호는 하나다 — 마지막 창에서는
    "다음" 버튼이 아예 사라진다(창 191~200 에서 사라졌고, 그 200페이지가 이
    그리드의 진짜 끝이었다: 마지막 행 '전북특별자치도 부안군').

    처음엔 "마지막 페이지는 보통 덜 찬다"는 행 수 어림으로 검증했는데, 실측에서
    이 그리드는 정확히 200페이지 × 50행이라 **마지막 페이지가 꽉 차 있었다** —
    멀쩡히 끝까지 걷고도 실패하는 오탐이었다. 그래서 어림을 버리고 페이저가
    스스로 알려주는 신호를 쓴다.
    """
    labels = _pager_labels(page)
    if _PAGER_NEXT_LABEL in labels:
        raise OlapPageWalkError(
            f"{visited}페이지에서 걷기를 멈췄는데 페이저에 아직 "
            f"'{_PAGER_NEXT_LABEL}' 버튼이 남아 있다 — 뒤에 페이지가 더 있다는 뜻이다 "
            f"(총 {page_count}페이지 읽음). 잘렸을 수 있는 그리드를 반환하지 않는다.")
    numbers = [int(text) for text in labels if text.isdigit()]
    if numbers and visited != max(numbers):
        raise OlapPageWalkError(
            f"마지막 창의 최대 페이지({max(numbers)})까지 걷지 못하고 {visited}페이지에서 "
            f"멈췄다 (총 {page_count}페이지 읽음). 잘렸을 수 있는 그리드를 반환하지 않는다.")


def _selected_page(page):
    """페이저가 표시하는 현재 페이지 번호. 못 읽으면 None."""
    labels = [text.strip() for text in
              page.eval_on_selector_all(_PAGER_SELECTED_SELECTOR, "els => els.map(e => e.innerText)")]
    numbers = [int(text) for text in labels if text.isdigit()]
    return numbers[0] if numbers else None


def _next_page_number(labels, visited: int):
    """창 안에서 아직 안 걸은 가장 작은 페이지 번호. 없으면 None."""
    larger = [int(text) for text in labels if text.isdigit() and int(text) > visited]
    return min(larger) if larger else None


def _body_after_render(page, prev_body):
    """페이지 클릭 뒤 본문이 실제로 바뀔 때까지 기다렸다가 돌려준다.

    끝내 안 바뀌면 prev_body 를 그대로 돌려준다 — 호출부가 "페이지가 안
    넘어갔다"로 보고 예외를 낸다.
    """
    body = prev_body
    for _ in range(_PAGE_RENDER_MAX_POLLS):
        page.wait_for_timeout(_PAGE_RENDER_POLL_MS)
        _, *body = page.evaluate(_EXTRACT_JS)
        if body and body != prev_body:
            return body
    return body


# 실측(2026-09-02, tools/probe_pagination_dedup_evidence.py)으로 확인된 EIS
# 페이지네이션 그리드의 요약 행 라벨 — 이 행들은 매 페이지 맨 위에 고정
# (pinned)되어 반복 렌더된다. 이 목록에 없는 라벨이 페이지를 넘나들며
# 반복되면(=진짜 데이터 행이 중복/손실됐을 수 있음) 개수와 무관하게 시끄럽게
# 실패한다 — 새로운 요약 라벨을 실측으로 확인하기 전에는 여기 추가하지 않는다.
# R16(2026-09-02, 리뷰 루프): "소계"/"합계"/"전체" 는 이 실측으로 확인된 적이
# 없어 뺐다 — 특히 "전체"는 실제 지역/범주 값으로도 그럴듯해서, 미확인 상태로
# 화이트리스트에 넣어두면 진짜 데이터 행을 요약 행으로 오분류해 조용히 본문에서
# 빼버릴 위험이 있었다(화이트리스트가 스스로 "확인 전엔 추가 안 한다"고 말하면서
# 확인 안 된 라벨을 이미 담고 있던 자기모순). 다른 보고서에서 소계 등이 실제로
# 고정 반복되는 게 확인되면, 그 전까지는 예외로 시끄럽게 실패하는 게 의도된
# 동작이다 — 그때 증거를 들고 이 목록에 추가한다.
_SUMMARY_ROW_LABELS = frozenset({"총계"})

# Task 15a 실측(2026-09-02, tools/probe_fetchers.py) — 중첩 축 그리드에는 그랜드
# 토탈 말고 **그룹 소계** 행도 있고, 그것도 페이지 경계를 넘나들며 반복 렌더된다
# (관측: `['서울특별시 전체', '서울특별시 전체', '0', '248,729']` 가 1·2페이지에
# 함께 등장). 라벨은 바깥 레벨 값 뒤에 " 전체" 가 붙은 모양이다. 위 화이트리스트가
# "실측으로 확인하기 전엔 추가하지 않는다"고 한 그 실측이 이번에 나온 것이라
# 여기 규칙으로 더한다 — 지역·직종·산업 이름 중 " 전체" 로 끝나는 것은 없으므로
# 진짜 데이터 행을 소계로 오분류할 위험은 낮다. 소계 행은 본문에서 빠져
# `Grid.summaries` 로 간다(더하면 이중계상이므로 본문에 남기면 안 된다).
_SUMMARY_ROW_SUFFIX = " 전체"

# 추출기가 덧붙이는 마지막 컬럼 — "이 행의 행-축 셀이 colspan 으로 레벨 여럿을
# 덮었는가"("1"/"0"). 실측(2026-09-03, 경력직이동 3·4페이지 경계): **같은 소계
# 행이 페이지 경계에서 두 번, 다르게 그려진다** — 3페이지 마지막에는
# `td('11차_숙박 및 음식점업', colspan=2)`, 4페이지 맨 위에는
# `td('11차_숙박 및 음식점업 전체', colspan=2, dx-row-total)` 로, 값은 둘 다
# 18,596 이다. 앞엣것은 잘린 렌더라 ' 전체' 접미도 클래스도 없어서 **텍스트로는
# 진짜 리프와 구별할 수 없다**(경력직이동에서 산업==산업(이전) 리프는 정상이다).
# 구별되는 것은 구조뿐이다: 집계 행은 레벨 여럿을 한 셀로 덮고, 리프는 레벨마다
# 자기 td 를 갖는다. 그 사실을 추정하지 않고 그대로 넘긴다.
AGGREGATE_COLUMN = "__집계__"


def _is_summary_label(text: str) -> bool:
    return text in _SUMMARY_ROW_LABELS or text.endswith(_SUMMARY_ROW_SUFFIX)


def _is_summary_row(row: list[str]) -> bool:
    """이 행이 (그랜드토탈이든 그룹 소계든) 요약 행인가 — **어느 칸이든** 본다.

    실측(2026-09-03, 경력직이동 202607): 중첩 축이 셋이면 **안쪽 레벨** 소계가
    페이지마다 고정 반복되는데, 그 행의 첫 칸은 진짜 시도다
    (`['서울특별시', '11차_전기…공급업 전체', '11차_전기…공급업 전체', '70']`).
    첫 칸만 보면 안 걸려서, 여섯 번째 실측 수집이 46분을 걷고 여기서 죽었다.
    `fetchers._is_aggregate_row` 가 이미 같은 규칙을 쓴다 — "시도는 '서울'인데
    산업 칸이 'C 제조업 전체'인 안쪽 레벨 소계는 이 규칙에서만 걸린다".

    진짜 데이터 행을 오분류하지 않는 근거: 지역·직종·산업 이름 중 " 전체" 로
    끝나는 것이 없고(접미 규칙은 앞에 이름과 공백을 요구하므로 값이 정확히
    "전체" 인 칸도 걸리지 않는다), 측정값 칸은 숫자다. mobility 에서 산업과
    산업(이전)이 같은 행은 정상인데, 그 칸들은 " 전체" 로 끝나지 않는다.
    """
    return any(_is_summary_label(cell) for cell in row)


class Grid(NamedTuple):
    """`_walk_paginated_grid`/`fetch_grid` 의 반환 타입 (R15, 리뷰 루프).

    이전엔 `_WithSummaries(list)` — list 를 상속해 `.summaries` 속성을 얹는
    방식이었다. 그런데 list 서브클래스의 인스턴스 속성은 슬라이싱·
    `list(x)`·`+`·컴프리헨션 등 어떤 list 연산을 거치기만 해도 조용히
    사라진다. 특히 자연스러운 다음 소비 패턴인 `parse_grid(fetch_grid(...))`
    는 예외도 에러도 없이 그냥 `list[dict]` 를 돌려주는데 총계가 이미
    사라진 뒤다 — R13 이 막으려던 바로 그 조용한 데이터 손실을 되살리는
    결함이었다. 그래서 명시적 타입(`typing.NamedTuple`)으로 바꿨다. 필드가
    3개(header/rows/summaries)라 옛 `header, *body = grid` 언패킹(대상 2개 +
    별표 1개)은 문법 자체는 여전히 통하지만 `body` 가 `[grid.rows,
    grid.summaries]`(리스트 두 개짜리)로 완전히 뒤바뀐다 — `body` 를 실제로
    쓰는 다음 줄(행을 순회하거나 `"".join(row)` 를 하는 등)에서 빠르게
    `TypeError` 로 깨진다. 조용한 손실보다 이렇게 호출부를 강제로 고치게
    만드는 시끄러운 깨짐이 낫다는 판단이다.

    `rows` 는 요약 행이 빠진 본문(R13), `summaries` 는 거기서 빠진 요약 행
    (총계 등, 없으면 빈 리스트)이다. `parse_grid` 에 넘기려면
    `parse_grid([grid.header, *grid.rows])` 처럼 명시적으로 조합해야 한다
    (parse_grid 시그니처는 R2 대로 손대지 않았다) — `parse_grid(grid)` 처럼
    `Grid` 를 그대로 넘기면 예외 없이 조합만 잘못된 `list[dict]` 를 돌려줄 수
    있으니, 반드시 `.header`/`.rows`(그리고 필요하면 `.summaries`)를 명시적으로
    골라 넘겨야 한다.
    """

    header: list[str]
    rows: list[list[str]]
    summaries: list[list[str]]


def _walk_paginated_grid(
    page, *, header: list[str], first_body: list[list[str]], pager_count: int
) -> Grid:
    """`.dx-datagrid-pager` 페이지 버튼을 순서대로 눌러가며 전 페이지를 누적한다.

    fetch_grid 가 이미 1페이지째를 읽어(header, first_body) pager_count>1 임을
    확인한 뒤에만 호출한다. 페이지 사이 `_PAGE_ADVANCE_WAIT_MS` 만큼 쉰다(정중함).

    반환(`Grid`, list 가 아니다 — R15)은 여러 독립된 기준으로 완전성이
    확인된 경우에만 이뤄진다:
      1. 페이지 이동마다 실제로 새 행이 보태졌는가 (안 그러면 클릭이 안 먹었거나
         이전/다른 페이지와 겹친 것).
      2. 마지막 페이지를 제외한 모든 페이지가 정확히 `_PAGE_SIZE` 행인가.
      3. 페이지를 넘나들며 반복된 행이 있다면, 그 행의 첫 칸이 알려진 요약 라벨
         (`_SUMMARY_ROW_LABELS`)인가 (R14) — 개수가 아니라 정체성으로 판단한다.
         아니면 그 행과 등장 페이지를 그대로 이름 붙여 예외를 낸다.
    허용된 요약 행(총계 등)은 본문에서 빼 `Grid.summaries` 로 따로 담는다
    (R13). 어느 기준이든 안 맞으면 조용히 넘어가지 않고 예외를 낸다.
    """
    if pager_count < 2:
        # 호출부(fetch_grid)가 이미 pager_count>1 일 때만 부르므로 정상 경로에서는
        # 닿지 않는다 — 방어적 불변식이다. 그래도 페이지 수를 못 정한 채 여기
        # 들어오면 조용히 진행하는 대신 시끄럽게 실패한다.
        raise OlapPageWalkError(
            f"페이지 수를 알아낼 수 없다 (pager_count={pager_count}) — "
            f"{_PAGER_SELECTOR} 로 페이지 버튼을 둘 이상 세지 못했다."
        )

    if not first_body:
        raise OlapExtractionError(
            "1페이지에 데이터 행이 하나도 없다 (헤더만 존재) — "
            "느린 렌더링이거나 필터/레이아웃이 잘못됐을 수 있다."
        )

    seen: dict[str, list[str]] = {}
    occurrences: dict[str, list[int]] = {}

    def _record(row: list[str], page_number: int) -> None:
        if not row:
            return
        key = "".join(row)
        seen[key] = row
        occurrences.setdefault(key, []).append(page_number)

    for row in first_body:
        _record(row, 1)

    prev_body = first_body
    page_sizes = [len(first_body)]
    visited = 1

    # R47 — 창을 넘겨가며 끝까지 걷는다. **종료 조건**은 하나다:
    # "지금 창에도, '다음'을 눌러 새로 드러난 창에도, 마지막으로 걸은 페이지보다
    # 큰 번호가 없다." 번호로만 이동하고 '다음'은 더 큰 번호를 **드러내는**
    # 용도로만 쓰므로, '다음'이 페이지를 한 칸 넘기든 창을 통째로 넘기든
    # 결과가 같다(둘 중 무엇인지는 실측하지 않았고, 알 필요가 없게 만든 것이다).
    # 'visited' 가 매 반복마다 반드시 커지므로 루프는 끝난다 — 그래도 페이저가
    # 이상하게 굴 때를 대비해 _MAX_PAGES 상한에서 예외를 낸다.
    while True:
        labels = _pager_labels(page)
        _check_pager_labels(labels)
        page_number = _next_page_number(labels, visited)
        if page_number is None:
            if _PAGER_NEXT_LABEL not in labels:
                break                      # 권위 있는 끝 — "다음"이 아예 없다
            # 창 넘김 클릭도 번호 클릭과 똑같이 이따금 먹지 않는다 — 실측
            # (2026-09-03): '다음' 은 창을 정상적으로 넘기는데(취업건수
            # 1-10 → … → 191-200) EIS 가 느려진 순간 30초 폴링 예산 안에
            # 라벨이 안 바뀌어, 200페이지를 다 걸을 수 있는 수집이 60페이지에서
            # 통째로 버려졌다. 번호 클릭이 이미 받는 보호(_PAGE_CLICK_ATTEMPTS)를
            # 여기에도 준다. 그래도 안 넘어가면 아래 예외는 그대로다.
            before = labels
            for _ in range(_PAGE_CLICK_ATTEMPTS):
                _click_pager_label(page, _PAGER_NEXT_LABEL)
                labels = _labels_after_window_move(page, before)
                if labels != before:
                    break
            _check_pager_labels(labels)
            page_number = _next_page_number(labels, visited)
            if page_number is None:
                raise OlapPageWalkError(
                    f"'{_PAGER_NEXT_LABEL}' 버튼이 있는데 눌러도 {visited}페이지보다 큰 "
                    f"번호가 나오지 않는다 (창: {labels}) — 창을 못 넘긴 것으로 보고 "
                    "잘렸을 수 있는 그리드를 반환하지 않는다.")
        if len(page_sizes) >= _MAX_PAGES:
            raise OlapPageWalkError(
                f"페이지를 {_MAX_PAGES}개까지 걸었는데도 끝이 안 난다 — 페이저가 "
                "제자리를 도는 것으로 보고 잘렸을 수 있는 결과를 반환하지 않는다.")

        # 실측(2026-09-03, insured 656페이지): 렌더가 예산을 넘기는 페이지가
        # 이따금 있다. 그때 같은 번호를 **다시 누르면** 이미 그 페이지라 아무
        # 일도 일어나지 않아 재시도가 오히려 실패를 확정한다. 그래서 다시 누르기
        # 전에 페이저가 표시하는 현재 페이지를 본다 — 이미 목표 페이지면 클릭은
        # 먹은 것이고 느릴 뿐이므로, 누르지 말고 더 기다린다.
        body = prev_body
        for attempt in range(_PAGE_CLICK_ATTEMPTS):
            if attempt and _selected_page(page) == page_number:
                body = _body_after_render(page, prev_body)
            else:
                _click_pager_label(page, str(page_number))
                body = _body_after_render(page, prev_body)
            if body and body != prev_body:
                break

        if not body:
            raise OlapExtractionError(
                f"{page_number}페이지가 데이터 행을 하나도 반환하지 않았다 — "
                "잘렸을 수 있는 그리드를 반환하지 않는다."
            )

        if body == prev_body:
            raise OlapPageWalkError(
                f"{page_number}페이지로 이동을 시도했지만 렌더된 행이 이전 "
                f"페이지와 똑같다 — "
                f"{_PAGER_SELECTOR} 클릭이 페이지를 못 넘겼을 수 있다."
            )

        before = len(seen)
        for row in body:
            _record(row, page_number)
        if len(seen) == before:
            # body != prev_body(위에서 이미 확인) 인데도 새 행이 하나도 안
            # 보태졌다 — 인접 페이지와 똑같지는 않지만(예: 순서만 바뀌었거나
            # 더 이전 페이지와 겹침) 실질적으로 아무 진전이 없었다는 뜻이라
            # 똑같이 "막혔다"고 본다.
            raise OlapPageWalkError(
                f"{page_number}페이지가 새 행을 하나도 보태지 못했다 (본문 "
                f"{len(body)}행 모두 이미 본 행이다) — 페이지가 실제로는 "
                "안 넘어갔거나 다른 페이지와 겹칠 수 있다."
            )

        page_sizes.append(len(body))
        prev_body = body
        visited = page_number

    _check_walk_completeness(page, visited, len(page_sizes))

    for i, size in enumerate(page_sizes[:-1], start=1):
        if size != _PAGE_SIZE:
            raise OlapPageWalkError(
                f"{i}페이지가 {size}행을 반환했다 — 마지막 페이지가 아닌데 "
                f"페이지 크기({_PAGE_SIZE})와 다르다. 페이지가 잘못 넘어갔을 "
                "수 있다."
            )

    # Task 7b Fix round 3 (컨트롤러 R14): 중복은 "몇 개까지 봐줄까"가 아니라
    # "무엇인가"로 판단한다. 실측(2026-09-02,
    # tools/probe_pagination_dedup_evidence.py)이 밝힌 진짜 원인은 그룹 헤더가
    # 페이지 경계에 걸쳐 다시 그려지는 게 아니라, 그랜드토탈(총계) 행이 매
    # 페이지 맨 위에 고정(pinned)되어 반복 렌더된다는 것이었다 — 옛 "중복 <=
    # 경계 수" 상한은 이번 사례(5중복=5경계)에서 숫자상 우연히 통과했을
    # 뿐이다. 그래서 중복된 행의 첫 칸이 알려진 요약 라벨
    # (_SUMMARY_ROW_LABELS)이면 통과시키고, 아니면(=실제 데이터 행이 반복됨)
    # 개수와 무관하게 그 행과 등장 페이지를 그대로 이름 붙여 예외를 낸다 —
    # 반복된 데이터 행은 그리드 구조를 이해하지 못했다는 뜻이므로 조용히
    # 넘어가지 않는다.
    summaries: dict[str, list[str]] = {}
    for key, pages in occurrences.items():
        if len(pages) <= 1:
            continue
        row = seen[key]
        if _is_summary_row(row):
            summaries[key] = row
            continue
        raise OlapPageWalkError(
            f"중복된 행이 있는데 알려진 요약 행 라벨"
            f"({sorted(_SUMMARY_ROW_LABELS)} 또는 '…{_SUMMARY_ROW_SUFFIX}')이 아니다: {row!r} "
            f"(페이지 {pages} 에서 반복 등장) — 반복된 데이터 행을 반환하면 "
            "그리드 구조를 잘못 이해했을 수 있으므로 반환하지 않는다."
        )

    # Task 7b Fix round 3 (컨트롤러 R13): 데이터 계약("유효구직건수의 분해값을
    # 더해 총계로 쓰지 않는다 — 총계는 총계 행에서 받는다")을 지키려면 허용된
    # 요약 행(위에서 걸러짐)을 본문에 섞어 반환하면 안 된다 — 그렇다고 버리지도
    # 않는다. 본문에서 빼 명시적 `Grid.summaries` 로 담아 돌려준다(R15: list
    # 서브클래스에 속성을 얹는 방식은 쓰지 않는다 — 조용히 사라질 수 있다).
    data_rows = [row for key, row in seen.items() if key not in summaries]
    return Grid(header=header, rows=data_rows, summaries=list(summaries.values()))


_EXTRACT_JS = r"""
() => {
  const AGGREGATE_COLUMN = "__집계__";
  function expandRow(tr) {
    const cells = Array.from(tr.querySelectorAll('td'));
    const out = [];
    for (const td of cells) {
      const span = parseInt(td.getAttribute('colspan') || '1', 10);
      const text = td.innerText.trim();
      for (let i = 0; i < span; i++) out.push(text);
    }
    return out;
  }

  // 열 머리 (마감년월 x 측정값) — 계층이 있으면 부모 라벨을 붙인다
  const headTrs = Array.from(document.querySelectorAll('thead.dx-pivotgrid-horizontal-headers tr'));
  const headRows = headTrs.map(expandRow);
  let colLabels = [];
  if (headRows.length) {
    const leaf = headRows[headRows.length - 1];
    colLabels = leaf.map((leafText, idx) => {
      const parents = headRows.slice(0, -1).map(r => r[idx]).filter(Boolean);
      return [...parents, leafText].filter(Boolean).join('_');
    });
  }

  // 행 머리 — 중첩 축이면 레벨마다 td 가 따로 있고, 바깥 레벨은 rowspan 으로
  // 그룹 첫 행에만 그려진다(Task 15a 실측). rowspan/colspan 을 펴서 레벨
  // 수만큼 칸을 항상 채운다 — 안 그러면 대부분의 행이 리프 라벨 하나뿐이라
  // (a) parse_grid 가 필드 이름을 어긋나게 붙이고, (b) 값이 같은 리프 행이
  // 서로 다른 그룹에서 문자열까지 똑같아져 fetch_grid 의 중복 제거에 조용히
  // 삼켜지거나 _walk_paginated_grid 가 "알 수 없는 중복"으로 죽는다.
  const rowFieldEls = Array.from(
    document.querySelectorAll('.dx-area-description-cell .dx-area-field-content'));
  const rowFields = rowFieldEls.map(el => el.innerText.trim()).filter(Boolean);
  const levels = Math.max(rowFields.length, 1);

  const rowLabelEls = Array.from(document.querySelectorAll('tbody.dx-pivotgrid-vertical-headers > tr'));
  const carry = new Array(levels).fill(null);
  const rowLabels = rowLabelEls.map(tr => {
    const cells = new Array(levels).fill(null);
    let spanned = false;
    for (let i = 0; i < levels; i++) {
      if (carry[i] && carry[i].left > 0) { cells[i] = carry[i].text; carry[i].left -= 1; }
    }
    const tds = Array.from(tr.querySelectorAll('td'));
    let t = 0;
    for (let i = 0; i < levels; i++) {
      if (cells[i] !== null) continue;
      if (t >= tds.length) break;
      const td = tds[t++];
      const text = td.innerText.trim();
      const rs = parseInt(td.getAttribute('rowspan') || '1', 10);
      const cs = parseInt(td.getAttribute('colspan') || '1', 10);
      for (let k = 0; k < cs && i + k < levels; k++) {
        cells[i + k] = text;
        if (rs > 1) carry[i + k] = { text: text, left: rs - 1 };
      }
      if (cs > 1 && levels > 1) spanned = true;
      i += cs - 1;
    }
    return {cells: cells.map(v => (v === null ? '' : v)), spanned: spanned};
  });

  // 데이터 셀
  const dataTrs = Array.from(document.querySelectorAll('.dx-pivotgrid-area-data table tbody tr'));
  const dataRows = dataTrs.map(tr =>
    Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim()));

  const header = [...(rowFields.length ? rowFields : ['지역']), ...colLabels,
                  AGGREGATE_COLUMN];

  const body = rowLabels.map((row, i) =>
    [...row.cells, ...(dataRows[i] || []), row.spanned ? '1' : '0']);
  return [header, ...body];
}
"""


def parse_grid(rows: list[list[str]]) -> list[dict]:
    """첫 행을 헤더로 삼아 [[str]] 를 [dict] 로 편다. (R2: 이 함수의 입력은 항상 list[list[str]])"""
    header, *body = rows
    return [dict(zip(header, row)) for row in body]


def fetch_grid(url: str, *, page, max_scrolls: int = 200, after_load=None) -> Grid:
    """Playwright page 로 뷰어를 열고 렌더된 PivotGrid 를 읽는다.

    반환은 `Grid(header, rows, summaries)` 다(R15) — list 가 아니므로 옛
    `header, *body = fetch_grid(...)` 언패킹은 더 이상 쓸 수 없다(의도적:
    `parse_grid` 에 넘기려면 `parse_grid([grid.header, *grid.rows])` 처럼
    명시적으로 조합해야 한다). 스크롤-누적 경로(페이저 없음)는 요약 행을
    따로 거르지 않으므로 `summaries` 가 항상 빈 리스트다 — 실측으로 그
    경로에서 고정 반복 요약 행 문제가 확인된 적이 없어서다.

    작은 표(예: 시도 단위, 17행)는 스크롤 없이 전량이 DOM 에 있는 것을 확인했다.
    dataScroll=Y 가상화가 걸리는 큰 표(예: 시군구 x 직종, 최대 약 2,450행)에
    대비해 데이터 영역을 끝까지 스크롤하며 고유 행을 누적한다 — 더 늘지 않으면
    멈춘다.

    max_scrolls=200 인 이유: 관측된 행 높이는 19px, 스크롤 한 번은 2000px 이므로
    한 번에 최대 ~105행 분량이 넘어간다. 예상 최대 워크로드(약 2,450행)를 덮으려면
    이론상 ~24회면 충분하지만, 실제 뷰포트/행 높이가 보고서마다 달라질 수 있어
    8배 안전 여유를 두고 브리프가 제시한 200을 그대로 썼다. 캡을 넉넉히 잡아도
    비용이 없다 — 정상적인 경우 행이 늘지 않는 순간 즉시 멈추기 때문이고, 캡이
    부족한 유일한 경우는 이제(아래) 조용히 잘린 결과 대신 예외를 낸다.

    반환은 **완전한 그리드임이 확인된 경우에만** 이뤄진다:
      - 그리드가 스크롤이 아니라 페이지네이션으로 나뉘어 있으면(Task 7 Step 0
        탐침: 행이 많은 레이아웃은 무한 스크롤이 아니라 `.dx-datagrid-pager`
        페이저를 쓴다 — 스크롤 누적은 첫 페이지만 본다) → 스크롤 대신
        `_walk_paginated_grid` 로 페이지 버튼을 순서대로 눌러가며 전 페이지를
        누적한다(Task 7b). 페이저 존재는 두 가지 독립된 방식으로 확인한다:
        (1) 페이저 컨테이너 자체를 명시적으로 기다린 뒤 세고, (2) 페이저가 안
        잡혔더라도 본문 행 수가 페이지 크기의 정확한 배수면 — 우연이라기엔
        너무 딱 맞아떨어지므로 — 탐지 실패로 보고 실패한다(모듈 수준 단일
        페이지로 오판하지 않기 위함). 타이밍에 기대는 건 (1)뿐이고, (2)는
        시간과 무관한 교차검증이다. 페이지 걷기 자체가 실패하면(클릭이 안
        먹거나, 어느 페이지가 비었거나, 요약 행이 아닌 행이 페이지를 넘나들며
        반복되면) `OlapPageWalkError`/`OlapExtractionError` 를 낸다
        (`_walk_paginated_grid` docstring 참고).
      - max_scrolls 를 다 써도 고유 행 수가 계속 늘면 → OlapExtractionError
      - 컨테이너는 렌더됐지만 데이터 행이 하나도 없으면 → OlapExtractionError
    """
    page.goto(url, wait_until="networkidle", timeout=90_000)

    # Task 15a — 그리드를 읽기 **전에** 축을 바꿀 자리. 화면이 요구하는 축
    # (시군구 × 직종 등)은 뷰어 URL 로는 못 얻고 좌측 필드초이서 드래그로만
    # 얻는데(pipeline/layout.py), 그 조작은 goto 와 추출 사이에 끼어야 한다.
    # 훅이 예외를 내면 그대로 위로 올린다 — 옛 축 그대로 읽어 가지 않는다.
    #
    # 이 훅은 그리드를 기다리기 **전에** 돈다. 실측(2026-09-03, 경력직이동):
    # 어떤 리포트는 조회를 누르기 전에 그리드가 아예 없다 — 그리드부터
    # 기다리면 60초를 다 쓰고 타임아웃으로 죽는다(첫 실측 수집에서 mobility 가
    # 그렇게 실패했다). 훅(set_layout)은 자기 전제인 좌측 필드초이서를 스스로
    # 기다리므로 여기서 대신 기다려 줄 것이 없다.
    if after_load is not None:
        after_load(page)

    page.wait_for_selector("div.dx-pivotgrid-area-data", timeout=60_000)

    # 페이저는 데이터 영역보다 늦게 뜰 수 있다. 고정 시간만 대기한 뒤 바로
    # 세면, 진짜 다중 페이지 그리드도 "아직 안 떴을 뿐"인데 "없다"고 오판해
    # 스크롤 누적으로 새 버려 첫 페이지만 조용히 반환할 위험이 있다 — 이
    # 모듈이 막으려는 바로 그 실수다. 그래서 페이저 컨테이너 자체를 명시적
    # 타임아웃으로 기다린다: 그 안에 뜨면 잡고, 끝까지 안 뜨면 그게 "없다"는
    # 증거다 (추측이 아니다).
    try:
        page.wait_for_selector(_PAGER_CONTAINER_SELECTOR, timeout=_PAGER_WAIT_MS)
    except Exception:  # noqa: BLE001 — 타임아웃까지 기다렸는데도 없다 = 진짜 없다
        pass

    pager_count = page.locator(_PAGER_SELECTOR).count()

    # R47 — 페이저를 걷기 전에 **구조를 아는지** 먼저 확인한다. `.dx-page` 는
    # 숫자 버튼 창 + "다음" 을 함께 세므로 그 개수는 전체 페이지 수가 아니다
    # (실측 텍스트 '12345678910다음'). 창 넘기기 자체는 _walk_paginated_grid 가
    # 하고, 여기서는 모르는 버튼이 섞여 있을 때 — 즉 페이저 구조가 바뀌어
    # 걷기가 조용히 잘릴 수 있을 때 — 시끄럽게 실패한다.
    if pager_count > 1:
        _check_pager_labels(_pager_labels(page))

    grid = page.evaluate(_EXTRACT_JS)
    header, *body = grid

    if pager_count > 1:
        # 스크롤 누적으로는 첫 페이지 분량만 보인다 — 페이지 버튼을 순서대로
        # 눌러가며 전 페이지를 누적한다(Task 7b). 완전성이 확인되지 않으면
        # _walk_paginated_grid 가 알아서 시끄럽게 실패한다.
        return _walk_paginated_grid(
            page, header=header, first_body=body, pager_count=pager_count
        )

    # 시간에 기대지 않는 교차검증: 페이저를 못 찾았는데도 본문 행 수가 정확히
    # 페이지 크기(_PAGE_SIZE)의 배수면, 데이터가 우연히 페이지 경계에서 끝났을
    # 가능성보다 페이저 탐지 자체(셀렉터 변경 등)가 실패했을 가능성이 훨씬
    # 크다 — 역시 조용히 넘어가지 않는다.
    if pager_count <= 1 and len(body) > 0 and len(body) % _PAGE_SIZE == 0:
        raise OlapPaginationError(
            f"페이저를 못 찾았는데 본문이 정확히 {_PAGE_SIZE}행 배수({len(body)}행)다 — "
            f"우연히 페이지 경계에서 끝났다고 보기보다 페이저 탐지 실패로 본다. "
            f"페이저 셀렉터({_PAGER_SELECTOR})가 바뀌었는지 확인하라."
        )

    seen: dict[str, list[str]] = {"".join(row): row for row in body if row}

    scroller = page.locator(
        "div.dx-pivotgrid-area-data .dx-scrollable-container"
    ).first

    stabilized = False
    for _ in range(max_scrolls):
        before = len(seen)
        try:
            scroller.evaluate("el => { el.scrollTop += 2000; }")
        except Exception:  # noqa: BLE001 — 스크롤 대상 자체가 없다: 가상화가 없는 작은 표로 간주
            stabilized = True
            break
        page.wait_for_timeout(200)
        grid = page.evaluate(_EXTRACT_JS)
        header, *body = grid
        for row in body:
            if row:
                seen["".join(row)] = row
        if len(seen) == before:
            stabilized = True
            break

    if not stabilized:
        raise OlapExtractionError(
            f"그리드가 안정화되지 않았다 — max_scrolls={max_scrolls} 를 다 써도 "
            f"행이 계속 늘어남 (수집된 고유 행 {len(seen)}개, 캡 {max_scrolls}회 도달). "
            "잘렸을 수 있는 그리드를 반환하지 않는다 — max_scrolls 를 늘리거나 "
            "가상화 동작을 다시 확인하라."
        )

    if not seen:
        raise OlapExtractionError(
            "그리드 컨테이너는 렌더됐지만 데이터 행이 하나도 없다 (헤더만 존재) — "
            "느린 렌더링이거나 필터/레이아웃이 잘못됐을 수 있다."
        )

    # 스크롤-누적(단일 페이지) 경로는 요약 행을 따로 거르지 않는다 — 페이지네이션
    # 경로(_walk_paginated_grid)와 달리 이 경로에서 요약 행이 고정 반복되는
    # 문제가 실측으로 확인된 적이 없다. summaries 는 빈 리스트로 둔다.
    return Grid(header=header, rows=list(seen.values()), summaries=[])


class ParsedGrid(NamedTuple):
    """`fetch_and_parse_grid` 의 반환 타입 (R15와 같은 이유로 명시적 타입).

    `Grid` 와 마찬가지로 list 서브클래스에 속성을 얹는 방식(예전
    `_WithSummaries`)은 슬라이싱 등을 거치면 `.summaries` 가 조용히 사라질 수
    있어 쓰지 않는다. `rows`/`summaries` 는 이미 `parse_grid` 를 거친
    `list[dict]` 다.
    """

    rows: list[dict]
    summaries: list[dict]


def fetch_and_parse_grid(url: str, *, browser, max_scrolls: int = 200,
                         after_load=None) -> ParsedGrid:
    """뷰어를 열어 그리드를 읽고 바로 dict 로 편다 (fetch_grid + parse_grid 를 잇는 이음매).

    반환은 `ParsedGrid(rows, summaries)` 다 — `fetch_grid` 가 돌려주는
    `Grid.header`/`Grid.rows`/`Grid.summaries` 를 각각 `parse_grid` 에
    명시적으로 조합해 넘긴다(총계 등 요약 행이 있으면 그것도 같은 방식으로
    파싱해 `.summaries` 로 그대로 넘긴다 — 조용히 버리지 않는다). `parse_grid`
    자체의 시그니처(list[list[str]] -> list[dict], R2)는 그대로다.
    """
    page = browser.new_page()
    try:
        grid = fetch_grid(url, page=page, max_scrolls=max_scrolls, after_load=after_load)
    finally:
        page.close()
    rows = parse_grid([grid.header, *grid.rows])
    summaries = parse_grid([grid.header, *grid.summaries]) if grid.summaries else []
    return ParsedGrid(rows=rows, summaries=summaries)
