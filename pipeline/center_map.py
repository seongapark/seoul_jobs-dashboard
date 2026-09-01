"""시군구를 센터로 묶는다.

이 매핑은 화면과 수집기가 함께 쓰는 유일한 지역 계약이다. 시군구 하나가 센터 둘에
붙으면 센터별 합계가 이중계상되므로 load 시점에 반드시 validate 한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CenterMap:
    _by_code: dict[str, str]
    _centers: tuple[str, ...]

    def center_of(self, sigungu_code: str) -> str:
        return self._by_code[sigungu_code]

    def codes(self) -> set[str]:
        return set(self._by_code)

    def centers(self) -> list[str]:
        return list(self._centers)

    def validate(self) -> None:
        if len(self._by_code) != 70:
            raise ValueError(f"시군구가 70개가 아니다: {len(self._by_code)}")
        if len(self._centers) != len(set(self._centers)):
            raise ValueError("센터 이름이 중복된다")


def load(path: Path) -> CenterMap:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    by_code: dict[str, str] = {}
    centers: list[str] = []
    for entry in raw["센터"]:
        name = entry["센터"]
        centers.append(name)
        for gu in entry["시군구"]:
            code = gu["code"]
            if code in by_code:
                raise ValueError(f"이중배정: {code} → {by_code[code]}, {name}")
            by_code[code] = name
    cm = CenterMap(by_code, tuple(centers))
    cm.validate()
    return cm
