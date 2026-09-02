# data/

- `center_map.json` — 시군구 → 고용센터 1:1 매핑 (70개 시군구, 39개 센터). 규칙은
  파일 안 `규칙` 배열 참고.
- `sigungu_names.json` — EIS 지역코드 팝업에서 받은 `{code: name}` 표. 경기 일반구
  코드와 폐지 코드는 `center_map.json` 에 없는 코드를 걸러내는 방식으로 이미
  제외했다 (70개만 남음). `pipeline/eis.py` 의 `SIGUNGU_NAME_TO_CODE` 가 이 파일을
  임포트 시 한 번 뒤집어서 만든다.
- `tile_layout.json` — 센터별 화면(Task 14)의 타일 카토그램 좌표표. 사람이 승인한
  목업(`.superpowers/sdd/2026-09-01-수도권-구인구직-대시보드/tile-layout-from-mockup.tsv`)
  의 70칸 배치를 그대로 옮긴 것이라 파이프라인 산출물이 아니다 — `sigungu_names.json`
  과 마찬가지로 이 저장소에 직접 커밋한다. `{code: {row, col, sido, name}}` 모양이고
  `name` 은 이미 시도 접두를 뗀 짧은 이름이다. 무결성(70개·코드 중복 없음·sido 는
  11/41/28 뿐)은 `app/tests/tilemap.test.js` 가 이 파일을 직접 읽어 검증한다.

## 센터 합계의 정의 (R4/R5)

**센터 합계 = 관할 시군구 값의 합이다.** EIS 에는 센터 축이 없어 이 방법 말고는
센터 단위 숫자를 낼 길이 없다.

단, **시도 단위 값은 시군구 합으로 만들지 않는다.** 유효구직건수는 1인이 여러
건을 낼 수 있어(1인 다건) 시군구별 값을 더하면 시도 총계보다 커진다. 시도 총계가
필요하면 `collect_vacancy_sido` / `collect_placement_sido` / `collect_insured_sido`
로 시도 단위 그리드를 따로 읽는다 (`pipeline/eis.py`).
