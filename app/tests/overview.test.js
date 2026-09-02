import { render } from "../js/screens/overview.js";
import { trend } from "../js/components.js";

// R20 — 시군구 store(vacancy/placement/insured)와 시도 store(vacancySido/
// placementSido/insuredSido)에 서로 다른 숫자를 넣어 둔다. 총괄이 시도가
// 아니라 시군구를 읽어버리면(축이 조용히 틀리는 실패) 아래 777777 이 화면에
// 나타난다 — 총괄은 이 값을 절대 보여주면 안 된다.
const SIGUNGU_SENTINEL = 777777;
const store = {
  vacancy: { period: "202607", rows: [
    { sigungu: "11110", center: "서울종로센터", vacancy: SIGUNGU_SENTINEL, seekers: SIGUNGU_SENTINEL },
  ] },
  placement: { period: "202607", rows: [
    { sigungu: "11110", center: "서울종로센터", placements: SIGUNGU_SENTINEL },
  ] },
  insured: { period: "202607", rows: [
    { sigungu: "11110", center: "서울종로센터", insured: SIGUNGU_SENTINEL, gained: SIGUNGU_SENTINEL, lost: SIGUNGU_SENTINEL },
  ] },
  vacancySido: { period: "202607", rows: [{ sido: "11", vacancy: 29196, seekers: 268616 }] },
  placementSido: { period: "202607", rows: [{ sido: "11", placements: 25233 }] },
  insuredSido: { period: "202607", rows: [{ sido: "11", insured: 4698520, gained: 193339, lost: 192131 }] },
  est: { period: "202601", rows: [{ sido: "11", size: "전규모", occupation: "", item: "채용계획인원", value: 109560 }] },
};

let failed = 0;
const has = (html, needle, label) => {
  if (!html.includes(needle)) { failed++; console.error(`FAIL ${label}`); }
  else console.log(`ok ${label}`);
};
const hasNot = (html, needle, label) => {
  if (html.includes(needle)) { failed++; console.error(`FAIL ${label}`); }
  else console.log(`ok ${label}`);
};
const eq = (got, want, label) => {
  if (got !== want) { failed++; console.error(`FAIL ${label}: ${got} !== ${want}`); }
  else console.log(`ok ${label}`);
};

const html = render(store, { sido: "11" });

has(html, "29,196", "유효구인이 보인다");
has(html, "268,616", "유효구직이 보인다");
has(html, "0.11", "구인배수가 계산된다");
has(html, "구인배수 &lt; 1 : 일자리 부족", "구인배수 각주가 붙는다");
has(html, "badge--est", "직종별사업체노동력조사는 주황 배지를 쓴다");
has(html, "109,560", "채용계획인원이 보인다");

// R20 — 총괄은 시도 store 를 읽는다, 시군구 store 가 아니다.
hasNot(html, String(SIGUNGU_SENTINEL), "총괄은 시군구 값을 보여주지 않는다 (시도 store 를 읽는다)");

// 화면 규칙 1 — 값이 없으면 카드째 감춘다. 전국 값을 대신 채우지도, 빈칸으로
// 두지도 않는다. insuredSido 행이 없으면 "고용보험 피보험자" 카드 자체가 없어야 한다.
const noInsured = {
  ...store,
  insuredSido: { period: "202607", rows: [] },
};
const htmlNoInsured = render(noInsured, { sido: "11" });
if (htmlNoInsured.includes("고용보험 피보험자")) {
  failed++;
  console.error("FAIL 피보험자 값이 없으면 카드가 통째로 빠진다");
} else {
  console.log("ok 피보험자 값이 없으면 카드가 통째로 빠진다");
}
// 그 사이 다른 값은 여전히 보여야 한다 — 카드 하나가 없다고 화면 전체가 죽지 않는다.
has(htmlNoInsured, "29,196", "다른 카드는 그대로 남는다");

// est 행이 아예 없으면(직종 소분류 선택 등) 채용계획인원 카드도 빠진다.
const noPlan = { ...store, est: { period: "202601", rows: [] } };
const htmlNoPlan = render(noPlan, { sido: "11" });
if (htmlNoPlan.includes("채용계획인원")) {
  failed++;
  console.error("FAIL 채용계획인원 값이 없으면 카드가 통째로 빠진다");
} else {
  console.log("ok 채용계획인원 값이 없으면 카드가 통째로 빠진다");
}

// R8 — components.trend: 두 계열을 한 축에 그리는 최소 인라인 SVG.
// 폴리라인 2개 + 끝점 원 2개 + 끝값 라벨, 범례는 카드 본문에 둔다. 두 y축은 없다.
const svg = trend({
  series: [
    { name: "유효구직건수", color: "#2a78d6", values: [250000, 260000, 268616] },
    { name: "유효구인인원", color: "#1baf7a", values: [28000, 28500, 29196] },
  ],
  labels: ["2026.05", "2026.06", "2026.07"],
});
const count = (needle) => (svg.match(new RegExp(needle, "g")) || []).length;

eq(count("<polyline"), 2, "두 계열의 선을 그린다");
eq(count("<circle"), 2, "각 계열 끝점에 점을 찍는다");
eq(count("viewBox"), 1, "한 축(뷰박스 하나)만 쓴다 — 두 y축을 쓰지 않는다");
has(svg, "268,616", "유효구직 끝값 라벨이 붙는다");
has(svg, "29,196", "유효구인 끝값 라벨이 붙는다");
has(svg, "유효구직건수", "범례에 계열 이름이 들어간다");
has(svg, "유효구인인원", "범례에 계열 이름이 들어간다");
has(svg, '<div class="legend">', "범례는 카드 본문에 둔다");

process.exit(failed ? 1 : 0);
