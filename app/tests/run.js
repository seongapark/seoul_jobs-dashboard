// app/tests/run.js — node 로 도는 최소 러너 (의존성 없음)
import { titleFor, ratio } from "../js/data.js";

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

process.exit(failed ? 1 : 0);
