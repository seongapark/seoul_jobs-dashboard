// app/tests/components.test.js — esc / bars / collapseCard / insuredBody / AXISLINE_HTML.
import { esc, bars, collapseCard, insuredBody, AXISLINE_HTML } from "../js/components.js";

let failed = 0;
const eq = (got, want, label) => {
  if (got !== want) { failed++; console.error(`FAIL ${label}: ${got} !== ${want}`); }
  else console.log(`ok ${label}`);
};
const has = (html, needle, label) => {
  if (!html.includes(needle)) { failed++; console.error(`FAIL ${label}`); }
  else console.log(`ok ${label}`);
};
const hasNot = (html, needle, label) => {
  if (html.includes(needle)) { failed++; console.error(`FAIL ${label}`); }
  else console.log(`ok ${label}`);
};

// --- esc (R24) ---------------------------------------------------------
eq(esc('<b>"x"&y</b>'), "&lt;b&gt;&quot;x&quot;&amp;y&lt;/b&gt;", "다섯 글자를 모두 이스케이프한다");
eq(esc(null), "", "null 은 빈 문자열");
eq(esc(undefined), "", "undefined 는 빈 문자열");

// --- bars ----------------------------------------------------------------
// 비율(최댓값을 100%로) — 소수 첫째 자리까지, 정확히 떨어지면 소수점을 안 붙인다.
const ratioHtml = bars({ items: [
  { label: "a", value: 4812 },
  { label: "b", value: 2406 }, // 정확히 절반
  { label: "c", value: 1000 }, // 4812분의 1000 ≈ 20.8%
] });
has(ratioHtml, "width:100%", "최댓값 항목은 100%");
has(ratioHtml, "width:50%", "절반 값은 50%(소수점 없이)");
has(ratioHtml, "width:20.8%", "비율이 소수 첫째 자리로 반올림된다");

// 최댓값이 0이면 전부 0%
const zeroHtml = bars({ items: [{ label: "a", value: 0 }, { label: "b", value: 0 }] });
eq((zeroHtml.match(/width:0%/g) || []).length, 2, "최댓값이 0이면 항목 전부 0%");

// mult 없으면 bar__mult 스팬 자체가 없다
const noMultHtml = bars({ items: [{ label: "a", value: 1 }] });
hasNot(noMultHtml, "bar__mult", "mult 가 없으면 bar__mult 자체를 안 넣는다");
const multHtml = bars({ items: [{ label: "a", value: 1, mult: 0.07 }] });
has(multHtml, '<span class="bar__mult">×0.07</span>', "mult 가 있으면 bar__mult 로 붙인다");

// highlighted → bar--hi, sub → bar--sub
const hiHtml = bars({ items: [{ label: "a", value: 1, highlighted: true }] });
has(hiHtml, "bar--hi", "highlighted 항목엔 bar--hi");
const subHtml = bars({ items: [{ label: "a", value: 1, sub: true }] });
has(subHtml, "bar--sub", "sub 항목엔 bar--sub");

// variant → 클래스 매핑
has(bars({ items: [{ label: "a", value: 1 }], variant: "jh" }), "bar--jh", "jh variant");
has(bars({ items: [{ label: "a", value: 1 }], variant: "est" }), "bar--est", "est variant");
const jo = bars({ items: [{ label: "a", value: 1 }] }); // 기본값
hasNot(jo, "bar--jh", "기본값(jo)은 별도 클래스가 없다");
hasNot(jo, "bar--est", "기본값(jo)은 별도 클래스가 없다");

// label 이 esc 를 통과한다
const escHtml = bars({ items: [{ label: '<b>"x"&y</b>', value: 1 }] });
has(escHtml, "&lt;b&gt;&quot;x&quot;&amp;y&lt;/b&gt;", "label 이 esc 를 통과한다");
hasNot(escHtml, "<b>", "raw html 이 그대로 들어가지 않는다");

// 값은 항상 막대에 직접 단다(화면 규칙 4)
has(ratioHtml, '<div class="bar__val num">4,812</div>', "값이 bar__val 에 붙는다");

// --- collapseCard ----------------------------------------------------------
const cc = collapseCard({ title: "제목", badge: "26.07", badgeClass: "badge--jh", body: "<p>내용</p>" });
has(cc, '<details class="card">', "details.card 로 감싼다");
has(cc, "sumname", "sumname 클래스가 있다");
has(cc, "badge--jh", "badgeClass 가 반영된다");
has(cc, "caret", "caret 표시가 있다");
has(cc, "자세히", "펼치기 문구가 있다");
has(cc, "<p>내용</p>", "body 가 그대로 들어간다");

// card() 와 같은 badgeClass 기본값
const ccDefault = collapseCard({ title: "제목", badge: "26.07", body: "x" });
has(ccDefault, "badge--jo", "badgeClass 기본값은 badge--jo");

// --- insuredBody (총괄 카드4 · 직종별 카드8 · 산업별 카드11 공용) --------
// 값 + 취득·상실·순증(순증 = 취득 − 상실). priorInsured 가 없으면
// 전년동월대비 줄이 아예 빠지고, 있으면 부호에 따라 is-up/is-down.
const ibBase = insuredBody({ insured: 800, gained: 60, lost: 25, priorInsured: undefined });
has(ibBase, '<div class="card__value num">800<small>명</small></div>', "피보험자 값이 붙는다");
has(ibBase, "취득", "취득 라벨");
has(ibBase, "60", "취득 값");
has(ibBase, "상실", "상실 라벨");
has(ibBase, "25", "상실 값");
has(ibBase, "+35", "순증 = 취득 − 상실, 양수면 + 부호");
hasNot(ibBase, "card__delta", "priorInsured 가 없으면 전년동월대비 줄이 안 붙는다");

const ibUp = insuredBody({ insured: 800, gained: 10, lost: 10, priorInsured: 700 });
has(ibUp, "card__delta", "priorInsured 가 있으면 전년동월대비 줄이 붙는다");
has(ibUp, "is-up", "늘었으면 is-up");
has(ibUp, "100", "증감 절댓값(800-700)");

const ibDown = insuredBody({ insured: 700, gained: 0, lost: 0, priorInsured: 800 });
has(ibDown, "is-down", "줄었으면 is-down");

// --- AXISLINE_HTML (스펙 §4.1, app.js 가 스위처 바로 뒤 한 곳에서만 쓴다) ---
has(AXISLINE_HTML, 'class="axisline"', "축 표기 줄에 목업 CSS 의 axisline 클래스를 쓴다");
has(AXISLINE_HTML, "<b>근무지역</b> 기준", "문구는 근무지역 기준이고 b 강조가 붙는다");

process.exit(failed ? 1 : 0);
