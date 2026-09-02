"""수집을 엮는다.

원칙: 검사를 다 통과한 뒤에야 파일을 쓴다. 절반만 갱신된 상태가 가장 나쁘다.

R4 — 시도 파일은 따로.
  시도 총계(예: vacancy_sido.json)는 시군구 값을 더해 만들지 않는다. 유효구직
  건수는 1인이 여러 희망근무지역을 낼 수 있어(1인 다건) 시군구 합이 시도
  총계보다 커질 수 있다 — 그 관계를 검산하는 건 checks.check_against_total
  의 몫이지, run_monthly 가 시군구를 더해 시도 값을 "만드는" 게 아니다.
  대신 fetchers 에 "<name>_sido" 키로 별도 수집기(예: eis.collect_vacancy_sido)
  를 넣으면 그 결과를 그대로 "<name>_sido.json" 에 쓴다. 시도 행은 sigungu
  가 아니라 sido 필드를 쓰므로(pipeline/eis.py 참고) 70개 시군구 완전성 검사·
  인천 개편 코드 검사 대상에서 뺀다 — 애초에 시군구가 아니다.

시군구 완전성 검사는 raw cm.codes() 70개를 그대로 쓰지 않는다 — 이유는
_effective_expected_codes 의 docstring 참고(요약: center_map.json 이 인천
개편 전후 코드를 영구히 함께 보존해서, raw 70개짜리 완전성은 실데이터로
"영원히" 만족 불가능하다).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline import checks

FIELD_OF = {"vacancy": "vacancy", "placement": "placements",
            "insured": "insured", "mobility": "movers"}

_SIDO_SUFFIX = "_sido"
_SIGUNGU_CHECKED = ("vacancy", "placement", "insured")


def _base_name(name: str) -> str:
    return name[: -len(_SIDO_SUFFIX)] if name.endswith(_SIDO_SUFFIX) else name


class _ExpectedCodes:
    """checks.check_regions 가 요구하는 `.codes()` 인터페이스만 제공하는 얇은 어댑터."""

    def __init__(self, codes: set[str]):
        self._codes = codes

    def codes(self) -> set[str]:
        return self._codes


def _effective_expected_codes(rows, cm):
    """cm.codes() 를 그대로 완전성 기준으로 쓰면 인천 개편 전후 코드가 매달
    함께 다 있어야 하는데, 그건 check_incheon_codes 가 금지하는 바로 그
    상황이다 — center_map.json 은 옛 코드(28110/28140/28260)를 과거 자료
    색인용으로 영구 보존하므로 70개 안에 개편 전·후가 함께 들어 있다. 즉
    raw cm.codes() 완전성은 실데이터로 "영원히" 만족될 수 없다(개편 이후엔
    옛 코드가 다시 나올 리 없으므로). 그래서 실제로 관측된 쪽 era 만
    요구하도록 완화한다 — 두 era 가 함께 관측되는 진짜 이상 상황은 여전히
    바로 다음 줄의 check_incheon_codes 가 잡는다. 이 조정이 없으면 매달
    수집이 영구히 실패한다.
    """
    seen = {row["sigungu"] for row in rows if "sigungu" in row}
    expected = set(cm.codes())
    for old, news in checks.INCHEON_OLD_TO_NEW.items():
        if old in seen and not any(new in seen for new in news):
            expected -= set(news)          # 아직 개편 전이다 — 신설 코드는 요구하지 않는다
        elif old not in seen and any(new in seen for new in news):
            expected.discard(old)          # 이미 개편됐다 — 옛 코드는 더는 요구하지 않는다
    return expected


def run_monthly(period, *, out_dir, fetchers, cm, previous=None):
    collected = {name: fetch(period) for name, fetch in fetchers.items()}

    for name, rows in collected.items():
        base = _base_name(name)
        field = FIELD_OF.get(base, base)
        if not name.endswith(_SIDO_SUFFIX) and base in _SIGUNGU_CHECKED:
            expected = _effective_expected_codes(rows, cm)
            checks.check_regions(rows, _ExpectedCodes(expected))
            checks.check_incheon_codes(rows)
        checks.check_not_all_zero(rows, field)
        checks.check_not_identical_to_previous(rows, (previous or {}).get(name))

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for name, rows in collected.items():
        (out_dir / f"{name}.json").write_text(
            json.dumps({"period": period, "collected_at": stamp, "rows": rows},
                       ensure_ascii=False),
            encoding="utf-8")
    return {name: len(rows) for name, rows in collected.items()}


def run_halfyear(period, *, out_dir, api_key, collector=None):
    from pipeline import est

    collector = collector or est.collect
    rows = collector([period], api_key=api_key)
    checks.check_est_seam(rows)
    checks.check_not_all_zero(rows, "value")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "est.json").write_text(
        json.dumps({"period": period, "rows": rows}, ensure_ascii=False),
        encoding="utf-8")
    return {"est": len(rows)}
