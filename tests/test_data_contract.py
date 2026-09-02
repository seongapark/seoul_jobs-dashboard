"""화면이 읽는 파일 목록 대 파이프라인 산출물 목록 — 이음매 계약 (R55).

이 파일이 있는 이유는 하나다. 최종 브랜치 리뷰가 찾은 Critical 둘(C1·C2)이
**둘 다 "각 조각은 옳은데 이음매에 아무도 없었다"** 였다:

  - C1 — 화면이 산업 선택지를 직종 축 파일에서 뽑아 목록이 영구히 비었다.
  - C2 — 산업별 KOSIS 수집기를 만들어 놓고 프로덕션 경로에 배선하지 않아
    산출물이 아예 없었다.

그리고 그때 있던 `test_every_screen_dataset_has_a_fetcher` 는 **하드코딩된
집합끼리 비교해** 둘 다 그냥 통과시켰다 — 사람이 손으로 적은 두 목록은 사람이
손으로 틀린 곳과 정확히 같이 틀린다. 그래서 이 테스트는 어느 쪽도 손으로 적지
않는다: 화면 목록은 `app/js/data.js` 를 실제로 읽어 뽑고, 산출물 목록은
`pipeline` 의 실제 표(MONTHLY_SPECS/SERIES_SPECS/HALFYEAR_SPECS)에서 뽑는다.

화면 규칙 1(값이 없으면 카드째 감춘다)이 이 종류의 결함을 완벽히 숨기기
때문에 — 카드가 사라져도 "원래 데이터가 없나 보다"로 읽힌다 — 기계가 대조하지
않으면 아무도 못 알아본다.
"""
from __future__ import annotations

import re
from pathlib import Path

from pipeline import cli, est, fetchers

ROOT = Path(__file__).resolve().parents[1]
DATA_JS = ROOT / "app/js/data.js"

# 파이프라인이 만들지 않고 **저장소에 커밋돼 있는** 참조 파일들. 화면은 이것도
# 읽지만 수집 산출물이 아니다(data/README.md 참고). 손으로 적는 유일한 목록이라
# 아래 테스트가 "정말 파일로 존재하는가"까지 확인한다 — 오타로 여기 넣어 두고
# 대조를 빠져나가는 길을 막는다.
COMMITTED_REFERENCE_FILES = {"center_map", "sigungu_names", "tile_layout"}


def _screen_files() -> dict[str, set[str]]:
    """`app/js/data.js` 의 FILE_OF/OPTIONAL_FILE_OF 를 실제로 읽어 파일명을 뽑는다."""
    source = DATA_JS.read_text(encoding="utf-8")
    out: dict[str, set[str]] = {}
    for table in ("FILE_OF", "OPTIONAL_FILE_OF"):
        found = re.search(rf"const {table} = \{{(.*?)\n\}};", source, re.S)
        assert found, f"{DATA_JS.name} 에서 {table} 표를 못 찾았다 — 화면 쪽 목록이 옮겨졌다"
        out[table] = set(re.findall(r'^\s*\w+:\s*"([^"]+)"', found.group(1), re.M))
    assert out["FILE_OF"], "FILE_OF 를 하나도 못 뽑았다 — 정규식이 형식 변화를 놓쳤다"
    assert out["OPTIONAL_FILE_OF"], "OPTIONAL_FILE_OF 를 하나도 못 뽑았다"
    return out


def _pipeline_outputs() -> set[str]:
    """파이프라인이 `data/` 에 쓰는 파일 이름(확장자 제외) 전부."""
    return set(fetchers.MONTHLY_SPECS) | set(fetchers.SERIES_SPECS) | set(cli.HALFYEAR_SPECS)


def test_every_file_the_screens_read_is_produced_or_committed():
    """C1 방향 — 화면이 읽는 파일 중 아무도 만들지 않는 것이 있으면 실패한다.

    그런 파일은 fetch 가 404 를 내고, 필수면 화면이 통째로 안 뜨고 선택이면
    카드가 조용히 사라진다.
    """
    screens = _screen_files()
    read = screens["FILE_OF"] | screens["OPTIONAL_FILE_OF"]
    orphans = read - _pipeline_outputs() - COMMITTED_REFERENCE_FILES
    assert not orphans, f"화면이 읽지만 아무도 만들지 않는 파일: {sorted(orphans)}"


def test_every_pipeline_output_is_read_by_a_screen():
    """C2 방향 — 만들어 놓고 아무도 안 읽는 산출물이 있으면 실패한다.

    이 방향이 C2 의 재발을 막는다: 산업별 KOSIS 표를 산출물 표에 넣고 화면
    배선을 잊으면(또는 그 반대면) 여기서 걸린다. 수집 비용(월 1회 브라우저
    수십 분)을 아무도 안 쓰는 파일에 들이는 것도 함께 막는다.
    """
    screens = _screen_files()
    read = screens["FILE_OF"] | screens["OPTIONAL_FILE_OF"]
    unread = _pipeline_outputs() - read
    assert not unread, f"파이프라인이 만들지만 어느 화면도 안 읽는 파일: {sorted(unread)}"


def test_committed_reference_files_really_exist():
    """위 손으로 적은 예외 목록이 유령 이름으로 대조를 빠져나가지 않게 한다."""
    for name in COMMITTED_REFERENCE_FILES:
        assert (ROOT / "data" / f"{name}.json").exists(), f"data/{name}.json 이 없다"


def test_optional_files_are_the_ones_that_may_not_exist_yet():
    """선택/필수 구분이 실제 수집 주기와 맞는가.

    시계열(`*_series`)과 산업 축, 반기 KOSIS 산업 표는 첫 수집 전에는 없을 수
    있어 선택이어야 한다(R31). 필수 목록에 들어가면 파일 하나가 없다는 이유로
    화면이 통째로 안 뜬다 — 카드 하나를 감추는 대신 앱이 죽는다.
    """
    screens = _screen_files()
    assert "vacancy_series" in screens["OPTIONAL_FILE_OF"]
    assert "est_industry" in screens["OPTIONAL_FILE_OF"]
    assert "est" in screens["FILE_OF"]


def test_every_est_collector_is_wired_to_an_output():
    """C2 를 정면으로 겨눈다 — 수집기를 만들고 부르는 곳이 테스트뿐이면 실패한다.

    est.collect_industry 는 R3 으로 만들어져 단위 테스트까지 통과했지만
    프로덕션 경로에 배선되지 않았다. "구현됐다"와 "실제로 돈다"는 다르다.
    """
    collectors = {name for name in dir(est) if name.startswith("collect")}
    wired = {spec.collector.__name__ for spec in cli.HALFYEAR_SPECS.values()}
    assert collectors == wired, (
        f"est 의 수집기와 반기 산출물 표가 어긋난다: 배선 안 됨 {sorted(collectors - wired)}")
