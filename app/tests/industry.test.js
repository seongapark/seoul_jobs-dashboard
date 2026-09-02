import { render } from "../js/screens/industry.js";

// 산업별 화면 — 컨트롤러가 다시 쓴 브리프(task-13-brief.md) 전체가 유일한
// 요구사항이다. 직종별 화면(Task 12)의 쌍둥이지만 두 가지가 다르다:
// (1) 이 탭엔 구직이 없다 — 유효구직 문자열이 어디에도 나오면 안 된다.
// (2) 카드 12(경력직 이동)는 mobility 를 읽는데, 그 행은 시도 축이라
// row.sido === sido 로 거른다 — vacancyIndustry/insuredIndustry(시군구 축,
// sigungu.startsWith(sido))와 규칙이 다르다(R35, 이 화면에서 가장 틀리기
// 쉬운 지점). 서울(11)·경기(41) 행을 vacancyIndustry·insuredIndustry·
// mobility 세 곳 모두에 섞어 두 규칙이 실제로 갈리는지 확인한다.
const store = {
  vacancyIndustry: {
    period: "202607",
    rows: [
      // 업종A — 서울 두 시군구에 걸쳐 있다(카드 10 합산 검증용).
      { period: "202607", sigungu: "11110", center: "서울종로센터", industry: "업종A", vacancy: 1100, seekers: 550 },
      { period: "202607", sigungu: "11170", center: "서울용산센터", industry: "업종A", vacancy: 200, seekers: 50 },
      // 업종2~9 — 카드 10 상위 8 절단 확인용 나머지 8개 업종.
      ...Array.from({ length: 8 }, (_, i) => ({
        period: "202607", sigungu: "11110", center: "서울종로센터",
        industry: `업종${i + 2}`, vacancy: 1000 - i * 100, seekers: 1,
      })),
      // 경기 행 — 서울(11) 선택 시 절대 랭킹에 섞이면 안 된다(테스트 1).
      { period: "202607", sigungu: "41110", center: "경기센터", industry: "경기전용업종", vacancy: 999999, seekers: 1 },
      // 빈 industry 행 — 랭킹에서 빠져야 한다(테스트 8).
      { period: "202607", sigungu: "11110", center: "서울종로센터", industry: "", vacancy: 777777, seekers: 1 },
      // 악의적 이름 — 이스케이프 확인(테스트 9). 값이 작아 top8 밖으로
      // 밀려나므로 카드 10 랭킹이 아니라 카드 11 제목에서 esc()가 걸린다.
      { period: "202607", sigungu: "11110", center: "서울종로센터", industry: "<나쁜>업종", vacancy: 10, seekers: 5 },
    ],
  },
  insuredIndustry: {
    period: "202607",
    rows: [
      { period: "202607", sigungu: "11110", center: "서울종로센터", industry: "업종A", insured: 500, gained: 50, lost: 20 },
      { period: "202607", sigungu: "11170", center: "서울용산센터", industry: "업종A", insured: 300, gained: 10, lost: 5 },
      { period: "202607", sigungu: "41110", center: "경기센터", industry: "업종A", insured: 999999, gained: 999999, lost: 999999 },
      // "<나쁜>업종" 행 — 카드 11 제목 이스케이프용(테스트 9).
      { period: "202607", sigungu: "11110", center: "서울종로센터", industry: "<나쁜>업종", insured: 5, gained: 1, lost: 0 },
    ],
  },
  mobility: {
    period: "202607",
    rows: [
      { period: "202607", sido: "11", industry: "업종A", prev_industry: "이전업종1", movers: 80 },
      { period: "202607", sido: "11", industry: "업종A", prev_industry: "이전업종2", movers: 60 },
      { period: "202607", sido: "11", industry: "업종A", prev_industry: "이전업종3", movers: 40 },
      { period: "202607", sido: "11", industry: "업종A", prev_industry: "이전업종4", movers: 20 },
      { period: "202607", sido: "11", industry: "업종A", prev_industry: "이전업종5", movers: 10 },
      { period: "202607", sido: "11", industry: "업종A", prev_industry: "이전업종6(잘림)", movers: 5 },
      // 경기 mobility 행 — sido 축이라 sido==="41". 서울(11) 선택 시 절대
      // 섞이면 안 된다(R35, 테스트 4). movers 를 크게 줘서 섞이면 바로 티난다.
      { period: "202607", sido: "41", industry: "업종A", prev_industry: "경기전용이전업종", movers: 999999 },
    ],
  },
  est: {
    period: "202601",
    rows: [
      { period: "202601", sido: "11", size: "전규모", industry: "J", industry_name: "업종A", item: "채용인원", value: 3000 },
    ],
  },
  // industry 축이 없는 시계열(occupation 축과 마찬가지, R31/R32) — 전년동월대비는
  // 항상 못 붙는다.
  insuredSeries: { rows: [{ period: "202507", sido: "11", insured: 700 }] },
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

const html = render(store, { sido: "11", industry: "업종A" });

// 1. 카드 10 랭킹이 선택 시도 안에서만 집계된다 — 경기 행이 섞이지 않는다.
hasNot(html, "경기전용업종", "경기 전용 업종은 서울 랭킹에 안 나온다");
hasNot(html, "999,999", "경기 행의 값이 서울 랭킹에 안 섞인다");

// 카드 10이 유효구인 내림차순 상위 8개까지만 낸다: 업종A(1300)+업종2..9
// (1000..300)=9개 후보 중 가장 작은 "업종9"(300)이 잘려야 한다.
has(html, "산업 대분류별 유효구인", "카드 10 제목(축 이름으로 시작)");
has(html, "업종8", "8위(업종8, 400)는 상위 8 안에 든다");
hasNot(html, "업종9", "9위(업종9, 300)는 상위 8에서 잘린다");
has(html, "bar--hi", "선택 업종 막대에 bar--hi 가 붙는다");

// 2. store.vacancyIndustry 가 없으면 카드 10이 사라지고 화면이 깨지지 않는다.
const htmlNoVacancyIndustry = render({ ...store, vacancyIndustry: undefined }, { sido: "11", industry: "업종A" });
hasNot(htmlNoVacancyIndustry, "산업 대분류별 유효구인", "vacancyIndustry 가 없으면 카드 10이 통째로 빠진다");
has(htmlNoVacancyIndustry, "피보험자", "카드 10이 없어도 카드 11은 남는다");

// store.insuredIndustry 가 없으면 카드 11도 마찬가지로 사라진다(카드 10과
// 뒤섞여 판단되지 않는다는 뜻이기도 하다).
const htmlNoInsuredIndustry = render({ ...store, insuredIndustry: undefined }, { sido: "11", industry: "업종A" });
hasNot(htmlNoInsuredIndustry, "피보험자", "insuredIndustry 가 없으면 카드 11이 통째로 빠진다");
has(htmlNoInsuredIndustry, "산업 대분류별 유효구인", "카드 11이 없어도 카드 10은 남는다");

// 3. 카드 11 피보험자가 시군구 합이고 취득·상실·순증을 낸다:
// 500+300=800, 취득 50+10=60, 상실 20+5=25, 순증 60-25=35(41110 의 999999 제외).
has(html, "800", "피보험자 합계(서울만)");
has(html, "취득", "취득 라벨");
has(html, "60", "취득 합계");
has(html, "상실", "상실 라벨");
has(html, "25", "상실 합계");
has(html, "순증", "순증 라벨");
has(html, "+35", "순증 = 취득 − 상실");
hasNot(html, "card__delta", "산업 축 시계열이 없어 전년동월대비는 안 붙는다");

// 4. 카드 12가 시도로 걸러진다 — 경기 mobility 행이 서울 값에 섞이지 않는다(R35).
hasNot(html, "경기전용이전업종", "경기 mobility 행의 라벨이 안 섞인다");
hasNot(html, "999,999", "경기 mobility 행의 값이 안 섞인다(중복 방지: 카드 10과 별개로도 확인)");

// 5. 카드 12 막대 라벨이 prev_industry 다 — movers 내림차순 상위 5, 6번째는 잘린다.
has(html, "경력직 이동", "카드 12 제목");
has(html, "이전업종1", "1위 이전 업종 라벨");
has(html, "이전업종5", "5위(상위 5)까지는 나온다");
hasNot(html, "이전업종6", "6위는 상위 5에서 잘린다");
has(html, "이전 업종", "카드 12 설명 한 줄이 붙는다");

// 6. 카드 13이 industry_name 으로 조인되고, 안 맞으면 사라진다.
has(html, "채용인원", "industry_name 이 맞으면 카드 13이 나온다");
has(html, "3,000", "채용인원 값");
const htmlNoEst = render(store, { sido: "11", industry: "업종2" });
hasNot(htmlNoEst, "채용인원", "industry_name 이 안 맞으면 카드 13이 통째로 빠진다");
// 그 사이 다른 카드(10)는 여전히 살아 있다.
has(htmlNoEst, "산업 대분류별 유효구인", "카드 13이 없어도 카드 10은 남는다");

// 7. 화면 어디에도 "유효구직" 문자열이 없다 — 이 탭엔 구직이 없다.
hasNot(html, "유효구직", "이 화면 어디에도 유효구직이 나오지 않는다");

// 8. industry 가 빈 문자열인 행은 랭킹에서 빠진다.
hasNot(html, "777,777", "빈 문자열 industry 행의 값이 랭킹에 섞이지 않는다");

// 9. "<" 가 든 업종 이름으로 이스케이프를 단언한다(카드 11 제목에서 걸린다 —
// 카드 10 랭킹에는 값이 작아(10) top8 밖으로 밀려 등장하지 않는다).
const htmlBad = render(store, { sido: "11", industry: "<나쁜>업종" });
hasNot(htmlBad, "<나쁜>업종", "업종 이름의 raw HTML 이 그대로 들어가지 않는다");
has(htmlBad, "&lt;나쁜&gt;업종", "업종 이름이 이스케이프되어 나온다");

// 시도에 그 업종 행이 아예 없으면(다른 시도만) 카드 10~13 전부 사라지고
// 화면이 깨지지 않는다(빈 컨테이너만 남는다).
const htmlEmptySido = render(store, { sido: "28", industry: "업종A" });
eq(htmlEmptySido, '<div class="cards"></div>', "데이터 없는 시도는 빈 카드 컨테이너만 낸다");

process.exit(failed ? 1 : 0);
