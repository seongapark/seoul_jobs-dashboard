import { esc } from "./components.js";

// 센터별 화면(Task 14)의 타일 카토그램. 이 모듈은 지도를 그리는 법만
// 안다 — 어떤 값을 넣을지, 카드에 어떻게 끼울지는 screens/center.js 몫이다
// (브리프 "Code Organization").

// 기본 5단계 경계값 — 구인배수(유효구인/유효구직) 분포에 맞춘 값이라
// screens/center.js 가 그대로 쓴다. 호출부가 다른 지표를 칠하고 싶으면
// breaks 를 바꿔 넘기면 된다.
const DEFAULT_BREAKS = [0.08, 0.12, 0.18, 0.25];

// 값 -> 1..5 단계. breaks[i] "이상"이면 다음 단계로 올라간다(경계값 자체는
// 그 위 단계다) — 예: breaks=[0.08,…] 일 때 0.08 은 2단계다.
export function step(value, breaks) {
  let level = 1;
  for (const b of breaks) {
    if (value >= b) level++;
    else break;
  }
  return level;
}

// 시도(행정표준코드 앞 두 자리) -> CSS 램프 변수 접두. 31(KOSIS 코드)은
// 여기 없다 — 이 저장소는 41(경기)만 쓴다(R9).
const RAMP_OF_SIDO = { 11: "s", 41: "g", 28: "i" };

// scope 칩 라벨 -> 그 시도만 남기는 필터 코드. "수도권"은 필터 없음을
// 뜻하므로 표에 없다.
const SIDO_OF_SCOPE = { 서울: "11", 경기: "41", 인천: "28" };

// values: { [시군구코드]: 구인배수 } — 코드가 없으면(undefined) "값 없음"
// 회색 타일로 그린다. layout: data/tile_layout.json 모양({ code: {row,col,
// sido,name} }).
export function render(values, layout, { breaks = DEFAULT_BREAKS, selected, scope, navOf } = {}) {
  const scopeSido = scope ? SIDO_OF_SCOPE[scope] : undefined;

  const tiles = Object.entries(layout)
    .filter(([, tile]) => !scopeSido || tile.sido === scopeSido)
    .map(([code, tile]) => {
      const value = values[code];
      const hasValue = value != null;
      // 값이 없으면 램프색을 아예 쓰지 않는다(var(--border), 은은한 회색) —
      // 1단계 색을 칠하면 "값 없음"이 "가장 낮은 값"으로 읽혀 지도가
      // 거짓말한다.
      const background = hasValue
        ? `var(--${RAMP_OF_SIDO[tile.sido]}${step(value, breaks)})`
        : "var(--border)";
      // 화면 규칙 5 — 초록(구인)이 배경 대비 2.74:1 이라 색만으로는 못
      // 읽는다. title/aria-label 에 값을 그대로 말로 적는다.
      const label = hasValue ? `${tile.name} 구인배수 ${value}` : `${tile.name} (값 없음)`;
      const onClass = selected === code ? " on" : "";
      const nav = navOf ? navOf(code) : "";

      return `<i class="tile${onClass}" role="button" tabindex="0" title="${esc(label)}" aria-label="${esc(label)}" data-code="${code}" data-nav="${esc(nav)}" style="grid-area:${tile.row}/${tile.col}; background:${background}"></i>`;
    })
    .join("");

  // 타일 하나하나가 이미 role="button" 이라 지도 전체엔 role="img" 을 주지
  // 않는다 — 대신 컨테이너에 무슨 지도인지만 밝혀 둔다.
  return `<div class="tilemap" aria-label="수도권 시군구 구인배수 타일 지도">${tiles}</div>`;
}
