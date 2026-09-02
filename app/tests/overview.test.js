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
  vacancySido: { period: "202607", rows: [
    { sido: "11", vacancy: 29196, seekers: 268616 },
    { sido: "41", vacancy: 48938, seekers: 317754 },
    { sido: "28", vacancy: 9268, seekers: 86627 },
  ] },
  placementSido: { period: "202607", rows: [{ sido: "11", placements: 25233 }] },
  insuredSido: { period: "202607", rows: [{ sido: "11", insured: 4698520, gained: 193339, lost: 192131 }] },
  est: { period: "202601", rows: [{ sido: "11", size: "전규모", occupation: "", item: "채용계획인원", value: 109560 }] },
  // R31 — Task 9b 가 낸 마감년월 축 시계열(시도만, occupation 축 없음).
  vacancySeries: { rows: [
    { period: "202605", sido: "11", vacancy: 28000, seekers: 260000 },
    { period: "202606", sido: "11", vacancy: 28500, seekers: 264000 },
    { period: "202607", sido: "11", vacancy: 29196, seekers: 268616 },
  ] },
  // 전년동월대비(R32)가 찾는 12개월 전(202507) 행.
  insuredSeries: { rows: [{ period: "202507", sido: "11", insured: 4600000 }] },
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

// 카드 2(추세) — store.vacancySeries 가 있으면 나오고, 라벨은 오름차순,
// 값은 시계열의 실제 수치를 그대로 쓴다.
has(html, "유효구인 · 유효구직 추세", "시계열이 있으면 추세 카드가 나온다");
has(html, "2026.05~2026.07", "추세 카드 배지는 시계열 범위다");
// trend() 는 끝점만 라벨을 붙인다(components.js 계약) — 계열이 실제로
// 배선됐는지는 범례의 이름(unit) 문자열로 구분한다(pairCard 의 "유효구인인원"
// 표기와 겹치지 않는다).
has(html, "유효구인(명)", "추세 카드에 유효구인 계열이 배선된다");
has(html, "유효구직(건)", "추세 카드에 유효구직 계열이 배선된다");

// 시계열 파일 자체가 없으면(R31 — 아직 수집이 안 쌓였을 수 있다) 추세
// 카드는 통째로 사라지고, 다른 카드는 죽지 않는다.
const htmlNoVacancySeries = render({ ...store, vacancySeries: undefined }, { sido: "11" });
if (htmlNoVacancySeries.includes("추세")) {
  failed++;
  console.error("FAIL 시계열이 없으면 추세 카드가 통째로 빠진다");
} else {
  console.log("ok 시계열이 없으면 추세 카드가 통째로 빠진다");
}
has(htmlNoVacancySeries, "29,196", "추세 카드가 없어도 다른 카드는 그대로 남는다");

// 이 시도 행이 하나도 없어도(다른 시도만 있는 시계열) 마찬가지로 감춘다.
const htmlOtherSidoSeries = render(
  { ...store, vacancySeries: { rows: [{ period: "202607", sido: "41", vacancy: 1, seekers: 1 }] } },
  { sido: "11" });
if (htmlOtherSidoSeries.includes("추세")) {
  failed++;
  console.error("FAIL 이 시도의 시계열 행이 없으면 추세 카드가 빠진다");
} else {
  console.log("ok 이 시도의 시계열 행이 없으면 추세 카드가 빠진다");
}

// --- 수도권 비교 표 (스펙 §4.1, 카드 2 뒤 · 카드 3 앞) -----------------------
// I2 — 원장 어디에도 이 항목을 빼기로 한 판정이 없다. 누락이지 판단이 아니다.
has(html, "수도권 비교", "수도권 비교 표가 나온다");
has(html, '<table class="tbl"', "목업 CSS 의 .tbl 클래스를 쓴다");
has(html, "48,938", "경기 유효구인이 표에 들어간다");
has(html, "9,268", "인천 유효구인이 표에 들어간다");
has(html, "317,754", "경기 유효구직이 표에 들어간다");
has(html, "is-me", "선택한 시도 행이 강조된다");
// 순서: 스펙이 그린 자리 — 카드 2(추세) 뒤, 카드 3(취업건수) 앞.
const orderOk = html.indexOf("유효구인 · 유효구직 추세") < html.indexOf("수도권 비교")
  && html.indexOf("수도권 비교") < html.indexOf("취업건수");
eq(orderOk, true, "수도권 비교 표는 추세 카드 뒤, 취업건수 앞에 놓인다");

// 시도 파일에 행이 하나도 없으면 표도 카드째 사라진다(화면 규칙 1).
const htmlNoSido = render({ ...store, vacancySido: { period: "202607", rows: [] } }, { sido: "11" });
hasNot(htmlNoSido, "수도권 비교", "시도 행이 없으면 비교 표도 카드째 감춘다");
// 한 시도만 있어도 지어내 채우지 않는다 — 있는 행만 그린다.
const htmlOneSido = render(
  { ...store, vacancySido: { period: "202607", rows: [{ sido: "41", vacancy: 48938, seekers: 317754 }] } },
  { sido: "11" });
has(htmlOneSido, "수도권 비교", "한 시도만 있어도 표는 나온다");
has(htmlOneSido, "<td>경기</td>", "있는 시도 행은 그린다");
hasNot(htmlOneSido, "<td>서울</td>", "없는 시도 행을 지어내지 않는다");
// (29,196 은 추세 카드의 끝점 라벨로도 나오므로 값 문자열로는 판정하지 않는다.)

// 카드 4 전년동월대비(R32) — insuredSeries 에 12개월 전 같은 달이 있으면 붙는다.
has(html, "card__delta", "전년동월대비가 있으면 .card__delta 가 붙는다");
has(html, "is-up", "이번 값이 더 크면 is-up");
has(html, "98,520", "증감 절댓값이 표시된다");
has(html, "전년동월대비", "전년동월대비 라벨이 붙는다");

// insuredSeries 자체가 없거나 12개월 전 행이 없으면 그 줄만 빠지고 카드는 남는다.
const htmlNoInsuredSeries = render({ ...store, insuredSeries: undefined }, { sido: "11" });
hasNot(htmlNoInsuredSeries, "card__delta", "전년동월대비 행이 없으면 그 줄만 빠진다");
has(htmlNoInsuredSeries, "고용보험 피보험자", "전년동월대비가 없어도 카드 자체는 남는다");
has(htmlNoInsuredSeries, "4,698,520", "전년동월대비가 없어도 피보험자 값은 그대로 나온다");

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
