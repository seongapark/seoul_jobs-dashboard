import { render } from "../js/screens/occupation.js";

// 직종별 화면 — 스펙 §4.2(브리프가 다시 씀). 이 화면은 시군구 원자료
// (store.vacancy/placement/insured)를 직접 읽는다 — overview 와 달리 시도
// 파일이 없다. 그래서 지역 필터는 sigungu.startsWith(sido) 로 직접 건다
// (R22 — row.sido === sido 라고 쓰면 시군구 행엔 그 필드가 없어 모든 카드가
// 조용히 사라진다). 서울(11)과 경기(41) 행을 섞어 그 필터가 실제로 도는지
// 확인한다.
const store = {
  vacancy: {
    period: "202607",
    rows: [
      // 직종1 — 서울 두 시군구에 걸쳐 있다(카드 7 합산 검증용). 하나는
      // sigunguNames 표에 없는 코드(11999)를 써서 코드 폴백도 같이 본다.
      { sigungu: "11110", center: "서울종로센터", occupation: "직종1", industry: "산업A", vacancy: 1100, seekers: 550 },
      { sigungu: "11170", center: "서울용산센터", occupation: "직종1", industry: "산업A", vacancy: 200, seekers: 50 },
      { sigungu: "11999", center: "서울미상센터", occupation: "직종1", industry: "산업A", vacancy: 50, seekers: 10 },
      // 직종2 ~ 직종11 — 카드 6 상위 10개 절단 확인용 나머지 10개 직종.
      ...Array.from({ length: 10 }, (_, i) => ({
        sigungu: "11110",
        center: "서울종로센터",
        occupation: `직종${i + 2}`,
        industry: "산업A",
        vacancy: 1000 - i * 100,
        seekers: (1000 - i * 100) * 2,
      })),
      // 경기 행 — 서울(11) 선택 시 절대 랭킹에 섞이면 안 된다(테스트 1).
      { sigungu: "41110", center: "경기센터", occupation: "경기전용직종", industry: "산업A", vacancy: 999999, seekers: 1 },
      // 악의적 이름 — 이스케이프 확인(테스트 9).
      { sigungu: "11110", center: "서울종로센터", occupation: "<나쁜>직종", industry: "산업A", vacancy: 10, seekers: 5 },
    ],
  },
  placement: {
    period: "202607",
    rows: [
      { sigungu: "11110", center: "서울종로센터", occupation: "직종1", placements: 300 },
      { sigungu: "11170", center: "서울용산센터", occupation: "직종1", placements: 40 },
      { sigungu: "41110", center: "경기센터", occupation: "직종1", placements: 999999 },
    ],
  },
  insured: {
    period: "202607",
    rows: [
      { sigungu: "11110", center: "서울종로센터", occupation: "직종1", industry: "산업A", insured: 500, gained: 50, lost: 20 },
      { sigungu: "11170", center: "서울용산센터", occupation: "직종1", industry: "산업A", insured: 300, gained: 10, lost: 5 },
      { sigungu: "41110", center: "경기센터", occupation: "직종1", industry: "산업A", insured: 999999, gained: 999999, lost: 999999 },
    ],
  },
  est: {
    period: "202601",
    rows: [
      { period: "202601", sido: "11", size: "전규모", occupation: "01", occupation_name: "직종1", item: "채용계획인원", value: 5000 },
    ],
  },
  // occupation 축이 없는 시계열(R31/R32) — 전년동월대비는 항상 못 붙는다.
  insuredSeries: { rows: [{ period: "202507", sido: "11", insured: 700 }] },
  sigunguNames: {
    "11110": "서울특별시 종로구",
    "11170": "서울특별시 용산구",
  },
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

const html = render(store, { sido: "11", occupation: "직종1" });

// 1. 카드 6 랭킹이 선택 시도 안에서만 집계된다 — 경기 행이 섞이지 않는다.
hasNot(html, "경기전용직종", "경기 전용 직종은 서울 랭킹에 안 나온다");
hasNot(html, "999,999", "경기 행의 값이 서울 랭킹에 안 섞인다");

// 2. 카드 6이 유효구인 내림차순 상위 10개까지만 낸다. 직종1(1350) + 직종2~11
// (1000..100) = 11개 후보 중 가장 작은 "직종11"(100)이 잘려야 한다.
has(html, "직종별 유효구인", "카드 6 제목(축 이름으로 시작)");
has(html, "직종10", "10위(직종10, 200)는 상위 10 안에 든다");
hasNot(html, "직종11", "11위(직종11, 100)는 상위 10에서 잘린다");

// 3. 선택 직종(직종1) 막대에 bar--hi 가 붙는다. 이 픽스처에서 highlighted 는
// 선택 직종 하나뿐이라 bar--hi 존재 자체가 배선 증거다.
has(html, "bar--hi", "선택 직종 막대에 bar--hi 가 붙는다");

// 4. 카드 7의 두 칸 값이 선택 시도 안 시군구 합이다: 1100+200+50=1350,
// 550+50+10=610 (41110 의 999999 는 제외).
has(html, "1,350", "카드 7 유효구인은 서울 시군구 합");
has(html, "610", "카드 7 유효구직은 서울 시군구 합");
// 취업건수도 서울만 합산: 300+40=340 (41110 의 999999 제외).
has(html, "340", "카드 7 취업건수도 서울 시군구 합");

// 5. 카드 7의 자치구별 막대가 선택 직종의 시군구 값만 쓴다 — 시도 접두를
// 뺀 짧은 이름, 표에 없는 코드는 코드 그대로.
has(html, "종로구", "자치구별 막대는 시도 접두를 뺀 이름을 쓴다");
has(html, "용산구", "두 번째 자치구도 짧은 이름으로 나온다");
has(html, "11999", "표에 없는 코드는 코드를 그대로 쓴다");
hasNot(html, "서울특별시", "자치구별 막대에 시도 접두가 남지 않는다");

// 6. 카드 8이 취득·상실·순증을 낸다. 500+300=800, 50+10=60, 20+5=25,
// 순증 60-25=35.
has(html, "800", "피보험자 합계(서울만)");
has(html, "취득", "취득 라벨");
has(html, "60", "취득 합계");
has(html, "상실", "상실 라벨");
has(html, "25", "상실 합계");
has(html, "순증", "순증 라벨");
has(html, "+35", "순증 = 취득 − 상실");
// occupation 축이 없는 시계열이라 전년동월대비 줄은 못 붙는다(R32).
hasNot(html, "card__delta", "직종 축 시계열이 없어 전년동월대비는 안 붙는다");

// 7. 카드 9는 occupation_name 이 맞을 때만 나온다.
has(html, "채용계획인원", "occupation_name 이 맞으면 카드 9가 나온다");
has(html, "5,000", "채용계획인원 값");
const htmlNoEst = render(store, { sido: "11", occupation: "직종2" });
hasNot(htmlNoEst, "채용계획인원", "occupation_name 이 안 맞으면(소분류 등) 카드 9가 통째로 빠진다");
// 그 사이 다른 카드(6)는 여전히 살아 있다 — 카드 하나가 빠져도 화면 전체가 죽지 않는다.
has(htmlNoEst, "직종별 유효구인", "카드 9가 없어도 카드 6은 남는다");

// 8. 시도에 그 직종 행이 아예 없으면(여기서는 그 시도 자체에 행이 없음)
// 카드 6·7·8·9 가 전부 사라지고 화면이 깨지지 않는다(빈 컨테이너만 남는다).
const htmlEmptySido = render(store, { sido: "28", occupation: "직종1" });
eq(htmlEmptySido, '<div class="cards"></div>', "데이터 없는 시도는 빈 카드 컨테이너만 낸다");

// 9. 직종 이름에 <가 들어간 악의적 픽스처로 이스케이프를 단언한다.
const htmlBad = render(store, { sido: "11", occupation: "<나쁜>직종" });
hasNot(htmlBad, "<나쁜>직종", "직종 이름의 raw HTML 이 그대로 들어가지 않는다");
has(htmlBad, "&lt;나쁜&gt;직종", "직종 이름이 이스케이프되어 나온다");

process.exit(failed ? 1 : 0);
