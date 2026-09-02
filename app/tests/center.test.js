import { render } from "../js/screens/center.js";
import { parseSelection } from "../js/data.js";

// 센터별 화면 — 컨트롤러가 다시 쓴 브리프(task-14-brief.md) 전체가 유일한
// 요구사항이다. 다른 화면과 결정적으로 다른 점: EIS 에 센터 축이 아예 없어
// (판정 R5) 센터 합계는 "관할 시군구 값의 합"으로 정의한다 — row.center 가
// 이미 센터 이름을 담고 있어 그대로 그룹 키로 쓴다. 그리고 이 화면 전체가
// selection.occupation/industry 를 안 읽는다 — 이 라우트엔 그 스위처 자체가
// 없다(app.js 가 지역만 붙인다).
//
// 숫자는 전부 나눗셈이 딱 떨어지게 골랐다(막대 폭 %를 손으로 검산하려고):
// - 서울고용센터(11110 종로구) 두 직종 행 vacancy 600+400=1000, seekers
//   300+100=400 → 구인배수 2.5.
// - 서울강남고용센터(11680) vacancy 800, seekers 400 → 구인배수 2.0.
// - 수원고용센터(41110, 경기) vacancy 2000, seekers 500 — scope=서울일 때
//   반드시 빠져야 한다. 카드 16 랭킹에도 절대 안 섞여야 한다(값 999999로
//   섞이면 바로 티나게 해 둔다).
// - 인천고용센터(28110) vacancy 200, seekers 100 — scope=서울일 때 빠진다.
const store = {
  vacancy: {
    period: "202607",
    rows: [
      { sigungu: "11110", center: "서울고용센터", occupation: "상담", industry: "제조업", vacancy: 600, seekers: 300 },
      { sigungu: "11110", center: "서울고용센터", occupation: "영업", industry: "도소매업", vacancy: 400, seekers: 100 },
      { sigungu: "11680", center: "서울강남고용센터", occupation: "상담", industry: "제조업", vacancy: 800, seekers: 400 },
      { sigungu: "41110", center: "수원고용센터", occupation: "상담", industry: "제조업", vacancy: 2000, seekers: 500 },
      { sigungu: "28110", center: "인천고용센터", occupation: "상담", industry: "제조업", vacancy: 200, seekers: 100 },
    ],
  },
  // 카드 16 상위 산업 — occupation 축과 다른 그리드(브리프 명시)라 이
  // 행에는 occupation 이 없다. 수원(경기) 행은 서울고용센터 랭킹에 절대
  // 섞이면 안 된다(값이 커서 섞이면 바로 티난다).
  vacancyIndustry: {
    period: "202607",
    rows: [
      { sigungu: "11110", center: "서울고용센터", industry: "제조업", vacancy: 600, seekers: 300 },
      { sigungu: "11110", center: "서울고용센터", industry: "도소매업", vacancy: 400, seekers: 100 },
      { sigungu: "41110", center: "수원고용센터", industry: "제조업", vacancy: 999999, seekers: 1 },
    ],
  },
  // 구 이름은 tile_layout.json 의 name(파생 사본)이 아니라 정본인 이
  // 표에서 뽑는다(브리프 명시, 리뷰 지적) — 그래서 tileLayout.name 과
  // sigunguNames 를 일부러 다르게 둬(예: "종로구" vs "서울특별시 종로구")
  // 화면이 실제로 이 표를 읽는지 구분해서 확인한다.
  sigunguNames: {
    "11110": "서울특별시 종로구",
    "11680": "서울특별시 강남구",
    "41110": "경기도 수원시",
    "28110": "인천광역시 중구",
    "11170": "서울특별시 용산구",
  },
  tileLayout: {
    "11110": { row: 1, col: 1, sido: "11", name: "종로구" },
    "11680": { row: 1, col: 2, sido: "11", name: "강남구" },
    "41110": { row: 2, col: 1, sido: "41", name: "수원시" },
    "28110": { row: 2, col: 2, sido: "28", name: "중구" },
    // 어느 store 행에도 안 나오는 시군구 — "값 없음" 처리 확인용.
    "11170": { row: 1, col: 3, sido: "11", name: "용산구" },
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
const ok = (cond, label) => {
  if (!cond) { failed++; console.error(`FAIL ${label}`); }
  else console.log(`ok ${label}`);
};

const base = {
  route: "center", sido: "11", scope: "수도권",
  occupation: "상담", industry: undefined, sigungu: undefined, center: undefined,
};

// 5·6. 선택 패널 — 타일을 눌러 시군구를 고르면 구 이름·센터 이름·대표
// 통계(유효구인·유효구직·구인배수)가 뜬다. 시군구 코드는 화면 텍스트로
// 절대 안 쓴다(코드는 data-nav/data-code 속성에만 남는다).
const htmlSel = render(store, { ...base, sigungu: "11110" });
has(htmlSel, "종로구", "선택 패널에 구 이름이 뜬다");
has(htmlSel, "서울고용센터", "선택 패널에 센터 이름이 뜬다");
hasNot(htmlSel, ">11110<", "시군구 코드가 화면 텍스트로 그대로 나오지 않는다");
has(htmlSel, '<dd class="num">1,000<small>명</small></dd>', "선택 시군구 유효구인 합(600+400)");
has(htmlSel, '<dd class="num">400<small>건</small></dd>', "선택 시군구 유효구직 합(300+100)");
has(htmlSel, '<dd class="num">2.5</dd>', "선택 시군구 구인배수(1000/400=2.5)");

// 선택이 없으면 안내 문구 한 줄, 값 없는 시군구도 지도엔 그려진다(랭킹은
// 안 깨진다 — 크래시 없음 자체가 증거).
const htmlNoSel = render(store, base);
has(htmlNoSel, "타일을 눌러 시군구를 선택하세요", "선택이 없으면 안내 문구가 뜬다");
has(htmlNoSel, "용산구", "값 없는 시군구도 지도에 그려진다");
has(htmlNoSel, "일자리 부족", "카드 14 에 구인배수 각주(RATIO_NOTE)가 붙는다");

// 7. 나비 막대 — 유효구인 내림차순, 좌우가 같은 눈금(두 계열 통틀어
// 최댓값 하나). scope=수도권 기준 전체 최댓값은 수원고용센터의 2000.
const htmlAll = render(store, base);
const iSuwon = htmlAll.indexOf('bf__c">수원<');
const iSeoul = htmlAll.indexOf('bf__c">서울<');
const iGangnam = htmlAll.indexOf('bf__c">서울강남<');
const iIncheon = htmlAll.indexOf('bf__c">인천<');
ok([iSuwon, iSeoul, iGangnam, iIncheon].every((i) => i !== -1), "카드 15 센터 라벨 4개가 모두 나온다");
ok(iSuwon < iSeoul && iSeoul < iGangnam && iGangnam < iIncheon,
  "센터가 유효구인 내림차순(수원 2000 > 서울 1000 > 강남 800 > 인천 200)");
// 같은 눈금 검증: max=2000 기준 — 수원 유효구인 2000→100%, 유효구직 500→25%.
// 좌우가 서로 다른 눈금이면(예: 각 계열 자기 최댓값 기준) 이 25%가 다른
// 값으로 나온다 — 이 화면에서 유일하게 25%가 나올 수 있는 값이다.
has(htmlAll, "width:100%", "최댓값(수원 유효구인)이 100% 폭");
has(htmlAll, "width:25%", "수원 유효구직 25%(500/2000) — 좌우가 한 눈금을 공유한다는 증거");

// 8. scope 칩이 막대 목록을 실제로 거른다 — scope=서울이면 경기·인천
// 센터가 카드 15 목록에서 빠진다. bf__c 로 네임스페이스를 좁혀서 찾는다 —
// 칩 목록 자체엔 "수도권·서울·경기·인천" 라벨이 항상 다 있어야 하므로
// (칩은 필터를 되돌릴 수 있어야 한다) 일반 hasNot("인천")은 못 쓴다.
const htmlSeoulScope = render(store, { ...base, scope: "서울" });
hasNot(htmlSeoulScope, 'bf__c">수원<', "scope=서울 이면 경기 센터가 카드 15에서 빠진다");
hasNot(htmlSeoulScope, 'bf__c">인천<', "scope=서울 이면 인천 센터가 카드 15에서 빠진다");
has(htmlSeoulScope, 'bf__c">서울<', "scope=서울 이면 서울고용센터는 그대로 나온다");
has(htmlSeoulScope, "chip--on", "현재 scope 칩에 chip--on 이 붙는다");
// 칩 자체는 필터와 무관하게 4개 다 남아 있다(되돌릴 수 있어야 하므로).
has(htmlSeoulScope, ">인천<", "scope=서울이어도 칩 목록엔 인천 칩이 남아 있다");
// scope 필터링 후 카드 15 안에서 눈금이 다시 그 안의 최댓값(서울고용센터
// 1000)으로 맞춰진다.
has(htmlSeoulScope, "width:100%", "scope 필터링 후에도 그 안에서 눈금이 다시 맞춰진다");

// 선택 시군구(11110, 서울고용센터 관할)가 속한 센터 막대에 is-sel.
const htmlSelBar = render(store, { ...base, sigungu: "11110" });
has(htmlSelBar, "is-sel", "선택 시군구가 속한 센터 막대에 is-sel 이 붙는다");

// 9. 카드 16 — 선택 센터가 있을 때만 나오고, 스위처(occupation/industry)를
// 따르지 않는다.
const html16 = render(store, { ...base, center: "서울고용센터" });
has(html16, "<details", "카드 16 은 collapseCard(접히는 카드)로 나온다");
has(html16, '<div class="subhead">상위 산업</div>', "카드 16 상위 산업 소제목");
has(html16, "제조업", "상위 산업 1위(제조업 600)");
has(html16, "도소매업", "상위 산업 2위(도소매업 400)");
hasNot(html16, "999,999", "다른 센터(수원)의 산업 값이 안 섞인다");
has(html16, '<div class="subhead">상위 직종</div>', "카드 16 상위 직종 소제목");
has(html16, "상담", "상위 직종 1위(상담 600)");
has(html16, "영업", "상위 직종 2위(영업 400)");

// 선택 센터가 없으면 카드 16이 통째로 빠진다(subhead 로 좁혀서 찾는다 —
// 카드 제목 자체가 "…상위 산업 · 직종"이라 bare "상위 산업"은 카드가
// 없어도 어차피 안 나오지만, 아래 절 단위 검사와 조건을 맞춰 둔다).
hasNot(htmlNoSel, '<div class="subhead">상위 산업</div>', "선택 센터가 없으면 카드 16이 통째로 빠진다");
hasNot(htmlNoSel, "<details", "선택 센터가 없으면 카드 16(details)이 아예 안 나온다");

// 카드 16의 감춤 판단은 hasValue() 하나를 거친다(리뷰 지적) — 정상 항해로는
// selection.center 가 항상 centerOfSigungu 에서 오므로 존재하는 센터만
// 들어오지만, 주소를 손으로 고쳐 존재하지 않는 센터 이름을 넣었을 때도
// "선택이 없다"와 같은 길로 감춰져야 한다(if(selection.center) 만 보면
// 이 경우 빈 막대 목록만 단 카드가 뜬다).
const htmlUnknownCenter = render(store, { ...base, center: "존재하지않는센터" });
hasNot(htmlUnknownCenter, "<details", "주소로 존재하지 않는 센터를 넣어도 카드 16이 감춰진다");
hasNot(htmlUnknownCenter, "존재하지않는센터", "그 센터 이름조차 화면에 안 남는다");

// 스위처 무관 — card16 부분(<details>…</details>)만 잘라서 비교한다.
// html16 전체를 그대로 비교하지 않는 이유: 카드 14·15의 타일/칩 data-nav 는
// selectionHash(selection)이 selection 객체 전체(occupation 포함)를 그대로
// 실어 나르므로 occupation 이 달라지면 그 속성값 자체가 달라진다 — 그건
// "선택을 왕복시키는 값"이 다른 것뿐이지 카드 16의 판단이 흔들린 게
// 아니다. card16 은 어떤 data-nav 도 없으므로 그 블록만 비교하면 판단
// 로직이 정말 occupation/industry 를 안 읽는지를 정확히 잰다.
const card16Of = (html) => html.match(/<details class="card">[\s\S]*<\/details>/)[0];
const sameOccu = render(store, { ...base, center: "서울고용센터", occupation: "영업" });
const sameIndu = render(store, { ...base, center: "서울고용센터", occupation: undefined, industry: "도소매업" });
eq(card16Of(html16), card16Of(sameOccu), "selection.occupation 을 바꿔도 카드 16 내용이 그대로다");
eq(card16Of(html16), card16Of(sameIndu), "selection.industry 를 바꿔도(occupation 을 지워도) 카드 16 내용이 그대로다");

// vacancyIndustry 가 없으면 상위 산업 절만 빠지고 상위 직종은 그대로 남는다.
const html16NoIndustry = render({ ...store, vacancyIndustry: undefined }, { ...base, center: "서울고용센터" });
hasNot(html16NoIndustry, '<div class="subhead">상위 산업</div>', "vacancyIndustry 가 없으면 상위 산업 절이 빠진다");
has(html16NoIndustry, '<div class="subhead">상위 직종</div>', "상위 산업이 빠져도 상위 직종은 남는다");
has(html16NoIndustry, "상담", "상위 직종 값 자체는 그대로");

// 10. 타일과 칩이 data-nav 를 달고, parseSelection 으로 되읽으면 의도한
// 선택이 나온다. HTML 엔티티(esc()가 '&'를 '&amp;'로 바꾼다)를 풀고
// 되읽는다.
const unescapeHtml = (s) => s
  .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
  .replace(/&quot;/g, '"').replace(/&#39;/g, "'");

const tileMatch = htmlNoSel.match(/data-code="11110"[^>]*data-nav="([^"]*)"/);
ok(!!tileMatch, "종로구 타일에서 data-nav 를 찾는다");
const tileSelection = parseSelection(unescapeHtml(tileMatch[1]));
eq(tileSelection.route, "center", "타일 data-nav 가 center 라우트를 유지한다");
eq(tileSelection.sigungu, "11110", "타일 data-nav 가 그 시군구 코드를 싣는다");

const chipMatch = htmlNoSel.match(/class="chip[^"]*"[^>]*data-nav="([^"]*)">서울</);
ok(!!chipMatch, "서울 칩에서 data-nav 를 찾는다");
const chipSelection = parseSelection(unescapeHtml(chipMatch[1]));
eq(chipSelection.scope, "서울", "칩 data-nav 가 그 scope 를 싣는다");

process.exit(failed ? 1 : 0);
