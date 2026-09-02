// app/tests/selection.test.js — parseSelection/selectionHash (R29/R30) 과
// Step 6b(data-nav) 가 기대는 왕복을, DOM 없이 문자열 수준에서 검증한다.
// optionsFor/reconcileForSido(R41)는 app.js 의 스위처가 쓰는 순수 로직이다
// — app.js 는 top-level 에서 main()이 곧장 돌며 document/fetch 를 찾으므로
// 노드에서 직접 import 해 테스트할 수 없다. 그래서 이 로직은 data.js 에
// 두고(순수 함수), app.js 는 그것을 불러 쓰기만 한다.
import { parseSelection, selectionHash, optionsFor, reconcileForSido, switcherRows } from "../js/data.js";

let failed = 0;
const eq = (got, want, label) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) { failed++; console.error(`FAIL ${label}: ${JSON.stringify(got)} !== ${JSON.stringify(want)}`); }
  else console.log(`ok ${label}`);
};

// --- 기본값 ---------------------------------------------------------------
eq(parseSelection("#/"), { route: "overview", sido: "11", scope: "수도권" },
   "빈 해시는 총괄·서울·수도권 기본값(occupation/industry/center/sigungu 는 undefined)");
eq(parseSelection(""), { route: "overview", sido: "11", scope: "수도권" }, "해시 자체가 없어도 같은 기본값");
eq(parseSelection(undefined), { route: "overview", sido: "11", scope: "수도권" }, "hash 가 undefined 여도 크래시 없이 기본값");

// --- 모르는 라우트 ----------------------------------------------------------
eq(parseSelection("#/badroute").route, "overview", "모르는 라우트는 총괄로 떨어진다");

// --- 없는 값은 undefined, 빈 문자열이 아니다 --------------------------------
// (빈 문자열이면 est 행의 실제 occupation:"" 과 조용히 오매칭된다.)
const parsed = parseSelection("#/occupation?sido=11");
eq(parsed.occupation, undefined, "없는 occupation 은 undefined");
eq(parsed.occupation === "", false, "빈 문자열로 만들지 않는다");

// --- scope ------------------------------------------------------------------
eq(parseSelection("#/center").scope, "수도권", "scope 기본값은 수도권");
eq(parseSelection("#/center?scope=서울").scope, "서울", "scope 지정값을 읽는다");
eq(parseSelection("#/center?scope=엉뚱").scope, "수도권", "모르는 scope 는 기본값으로 떨어진다");

// --- 한글·특수문자 인코딩 왕복 (R29 — 직종 이름에 · 와 괄호가 들어간다) -------
const withPunct = { route: "occupation", sido: "41", occupation: "안내·고객상담·통계·비서 및 기타 사무원(가나)" };
const hashWithPunct = selectionHash(withPunct);
eq(parseSelection(hashWithPunct).occupation, withPunct.occupation, "· 와 괄호, 공백이 있는 직종명이 인코딩 왕복한다");

// --- selectionHash 짝 — 전체 selection 이 왕복한다 --------------------------
const full = { route: "industry", sido: "41", industry: "제조업(자동차·부품)", scope: "경기" };
eq(parseSelection(selectionHash(full)), full, "전체 selection 이 selectionHash → parseSelection 으로 그대로 돌아온다");

// sigungu 왕복 (Task 14 의 지도 칩·타일이 쓸 값)
eq(parseSelection(selectionHash({ route: "center", sigungu: "11740" })).sigungu, "11740", "sigungu 가 왕복한다");

// overview 라우트는 해시에 라우트 세그먼트가 안 붙는다("#/" 그대로)
eq(selectionHash({ sido: "11" }), "#/?sido=11", "overview 는 경로 없이 쿼리만 붙는다");

// --- Step 6b: data-nav 문자열도 같은 selectionHash 를 쓰므로 같은 방식으로 왕복한다 ---
// (센터별 지도 타일이 찍을 값을 흉내낸다: data-nav="${selectionHash({...sel, sigungu: code})}")
const centerSel = { route: "center", scope: "서울" };
const navValue = selectionHash({ ...centerSel, sigungu: "11110" });
const roundTripped = parseSelection(navValue);
eq(roundTripped.route, "center", "data-nav 문자열이 route 를 왕복시킨다");
eq(roundTripped.scope, "서울", "data-nav 문자열이 scope 를 왕복시킨다");
eq(roundTripped.sigungu, "11110", "data-nav 문자열이 sigungu 를 왕복시킨다");

// --- optionsFor/reconcileForSido (R41 — 스위처 선택지는 지역으로 걸러야 한다) ---
//
// C1 — 픽스처를 **실제 두 파일 모양으로** 가른다. 직종 축 그리드
// (vacancy.json)와 산업 축 그리드(vacancy_industry.json)는 EIS 에서 서로 다른
// 레이아웃으로 따로 받는 별개의 파일이고, eis.collect_vacancy 는 그 그리드에
// 없는 축을 빈 문자열로 채운다 — 그래서 **한 행이 occupation 과 industry 를
// 함께 갖는 일은 실데이터에 없다.** 예전 픽스처가 둘을 한 행에 담는 바람에
// "산업 스위처가 직종 축 파일에서 선택지를 뽑아 목록이 영구히 빈다"는 결함
// (C1)이 테스트를 그냥 통과했다.
const vacancyRows = [
  { sigungu: "11110", occupation: "경영·행정·사무직", industry: "" },
  { sigungu: "11140", occupation: "생산직", industry: "" },
  { sigungu: "41111", occupation: "판매직", industry: "" },
  { sigungu: "41135", occupation: "", industry: "" }, // 빈 문자열은 est 전직종 합계 값 — 선택지에서 뺀다
];
const vacancyIndustryRows = [
  { sigungu: "11110", occupation: "", industry: "제조업" },
  { sigungu: "11140", occupation: "", industry: "건설업" },
  { sigungu: "41111", occupation: "", industry: "도소매업" },
  { sigungu: "41135", occupation: "", industry: "" },
];

eq(optionsFor(vacancyRows, "occupation", "11"), ["경영·행정·사무직", "생산직"],
   "서울(11)로 거르면 서울 시군구 행의 occupation 만, 가나다순");
eq(optionsFor(vacancyRows, "occupation", "41"), ["판매직"], "경기(41)로 거르면 경기 행만 남는다");
eq(optionsFor(vacancyIndustryRows, "industry", "41"), ["도소매업"], "industry 축도 같은 방식으로 거른다");
eq(optionsFor(vacancyRows, "occupation", "28"), [], "행이 없는 시도는 빈 목록(에러 없이)");

// C1 회귀 못 — 직종 축 파일에서 산업 선택지를 뽑으면 **어느 시도에서도** 빈다.
eq(optionsFor(vacancyRows, "industry", "11"), [],
   "직종 축 파일(vacancy)에는 산업 값이 없다 — 거기서 뽑으면 목록이 영구히 빈다(C1)");
eq(optionsFor(vacancyIndustryRows, "occupation", "11"), [],
   "산업 축 파일에는 직종 값이 없다 — 축과 파일은 짝이 맞아야 한다");

// --- switcherRows (C1 — 축마다 어느 파일을 읽는가) ---------------------------
const storeWithIndustry = {
  vacancy: { rows: vacancyRows },
  vacancyIndustry: { rows: vacancyIndustryRows },
};
eq(switcherRows(storeWithIndustry, "occupation"), vacancyRows, "직종 스위처는 직종 축 파일을 읽는다");
eq(switcherRows(storeWithIndustry, "industry"), vacancyIndustryRows, "산업 스위처는 산업 축 파일을 읽는다");
eq(switcherRows({ vacancy: { rows: vacancyRows } }, "industry"), undefined,
   "산업 축 파일이 없으면 undefined — 부르는 쪽이 select 자체를 안 내도록");
eq(optionsFor(switcherRows(storeWithIndustry, "industry"), "industry", "11"), ["건설업", "제조업"],
   "스위처 배선을 통째로 이어 보면 산업 목록이 실제로 채워진다");

eq(reconcileForSido(vacancyRows, { occupation: "생산직" }, "occupation", "11"), "생산직",
   "새 시도 목록에도 있으면 선택을 그대로 유지한다");
eq(reconcileForSido(vacancyRows, { occupation: "생산직" }, "occupation", "41"), "판매직",
   "새 시도 목록에 없으면 새 목록의 첫 값으로 떨어진다(조용히 빈 화면이 되지 않는다)");
eq(reconcileForSido(vacancyRows, { occupation: "생산직" }, "occupation", "28"), undefined,
   "새 목록이 아예 비어 있으면 undefined 로 떨어진다");
eq(reconcileForSido(vacancyRows, {}, "occupation", "41"), undefined,
   "이 라우트에 애초에 occupation 선택이 없으면 손대지 않는다");

process.exit(failed ? 1 : 0);
