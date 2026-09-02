// app/tests/selection.test.js — parseSelection/selectionHash (R29/R30) 과
// Step 6b(data-nav) 가 기대는 왕복을, DOM 없이 문자열 수준에서 검증한다.
import { parseSelection, selectionHash } from "../js/data.js";

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

process.exit(failed ? 1 : 0);
