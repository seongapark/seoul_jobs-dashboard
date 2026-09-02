// app/tests/data.test.js — data.js 의 titleFor/ratio/hasValue.
// (parseSelection/selectionHash 는 selection.test.js, load() 는 브라우저
// fetch 에 기대 노드 테스트로 못 덮는다.)
import { titleFor, ratio, hasValue, staleNotice, STALE_AFTER_DAYS } from "../js/data.js";

let failed = 0;
const eq = (got, want, label) => {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) { failed++; console.error(`FAIL ${label}: ${got} !== ${want}`); }
  else console.log(`ok ${label}`);
};

eq(titleFor("02 경영·행정·사무직", "피보험자"), "02 경영·행정·사무직 피보험자", "12자 이하는 그대로");

// R7 — 기대값을 문자열 상수로 박지 않고 규칙 자체로 계산해 단언한다.
const long = "029 안내·고객상담·통계·비서 및 기타 사무원";
eq(titleFor(long, "피보험자"), long.slice(0, 12) + "… 피보험자", "12자 초과는 줄임");

// R7 — 12자 경계값을 별도로 핀한다: 12자는 그대로, 13자부터 줄인다.
const twelve = "가나다라마바사아자차카타"; // 정확히 12자
eq(titleFor(twelve, "구분"), `${twelve} 구분`, "정확히 12자는 줄이지 않는다");
const thirteen = twelve + "파"; // 정확히 13자
eq(titleFor(thirteen, "구분"), `${twelve}… 구분`, "13자부터는 줄인다");

eq(ratio(29196, 268616), 0.11, "구인배수는 소수 둘째 자리");
eq(ratio(0, 0), null, "분모가 0 이면 null");

// hasValue — 카드 감춤 규칙의 단일 판단점 (직종 소분류를 고르면 채용계획인원
// 카드가 사라지는 것도 이 함수 하나로 판단한다).
const estRows = [
  { sido: "11", occupation: "02", item: "채용계획인원", value: 26828 },
];
eq(hasValue(estRows, { sido: "11", occupation: "02", item: "채용계획인원" }), true,
   "selection 에 맞는 행이 있으면 true");
eq(hasValue(estRows, { sido: "11", occupation: "026", item: "채용계획인원" }), false,
   "직종 소분류처럼 맞는 행이 없으면 false");
eq(hasValue([], { sido: "11" }), false, "행이 아예 없으면 false");
eq(hasValue(undefined, { sido: "11" }), false, "rows 자체가 없어도 false (크래시 없이)");

// --- staleNotice (I4, 스펙 §5.2 "마지막 성공 시점") --------------------------
// 검사가 하나라도 어긋나면 수집은 커밋하지 않고 죽는다 — 기존 파일은 그대로
// 남는다. 그래서 수집이 석 달 실패해도 화면은 아무 말 없이 옛 기준월을 띄운다.
// 이 함수가 그 침묵을 깬다. `now` 를 주입받는 순수 함수라 시계 없이 검증된다.
const day = 24 * 60 * 60 * 1000;
const at = (iso) => ({ collected_at: iso });
const NOW = new Date("2026-09-02T00:00:00Z");
const ago = (days) => new Date(NOW.getTime() - days * day).toISOString();

eq(STALE_AFTER_DAYS, 45, "임계는 45일 — 월 1회 수집(매월 5일)이라 한 번 걸러도 드러난다");
eq(staleNotice(at(ago(3)), NOW), null, "막 수집했으면 배너가 없다");
eq(staleNotice(at(ago(44)), NOW), null, "임계 직전(44일)까지는 배너가 없다");
eq(staleNotice(at(ago(45)), NOW), null, "정확히 임계면 아직 아니다 — 넘어야 띄운다");
eq(typeof staleNotice(at(ago(46)), NOW), "string", "임계를 넘으면 문자열을 낸다");
eq(staleNotice(at(ago(100)), NOW).includes("2026.05.25"), true,
   "배너는 마지막 성공 시점을 날짜로 밝힌다");
eq(staleNotice(at(ago(100)), NOW).includes("100일"), true, "며칠째인지도 함께 밝힌다");

// collected_at 이 없거나 읽을 수 없으면 조용히 넘어가지 않는다 — 이 저장소의
// 원칙 그대로("조용히 틀리느니 시끄럽게"). 배너를 안 띄우면 "최신"과 구별이 안 된다.
eq(typeof staleNotice({}, NOW), "string", "collected_at 이 없으면 그 사실을 띄운다");
eq(typeof staleNotice(at("이건 날짜가 아니다"), NOW), "string", "못 읽는 값도 띄운다");
eq(typeof staleNotice(undefined, NOW), "string", "데이터셋 자체가 없어도 크래시 없이 띄운다");

process.exit(failed ? 1 : 0);
