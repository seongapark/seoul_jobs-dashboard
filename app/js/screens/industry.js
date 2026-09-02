import { card, bars, esc, num, insuredBody } from "../components.js";
import { hasValue, titleFor, period, half, inSido, sumBy } from "../data.js";

// 산업별 화면 — 컨트롤러가 다시 쓴 브리프(task-13-brief.md) §전체가 유일한
// 요구사항이다. 플랜 원문의 카드 3장 스케치는 실데이터 모양·공용 부품과
// 어긋나 폐기됐다.
//
// 직종별 화면(Task 12)의 쌍둥이지만 축이 다르다:
// - vacancyIndustry/insuredIndustry 는 시군구 원자료라 inSido()(sigungu 접두)로
//   거른다. mobility 는 시도 그 자체(row.sido)라 규칙이 다르다 — 이 둘을
//   섞으면(R35) 시군구 행이 전부 필터를 통과 못 하거나, mobility 행이 아예
//   안 걸러진다. 이 화면에서 가장 틀리기 쉬운 지점이라 카드마다 주석을 남긴다.
// - 이 탭엔 구직이 없다: 유효구인만 있고 구인배수·유효구직 칸이 없다.
// - 산업 축 수집(vacancy_industry.json/insured_industry.json)이 아직 배선
//   전이라(15a) store.vacancyIndustry/store.insuredIndustry 가 undefined 일
//   수 있다 — 그때 카드 10·11이 통째로 감춰지는 게 정상이다(hasValue 가
//   undefined rows 를 false 로 처리해 알아서 감춘다).
// - est 는 industry 코드/이름이 갈리므로 조인은 industry_name 으로 한다(R33).

export function render(store, selection) {
  const name = selection.industry;
  const cards = [];

  const sidoVacancyIndustry = store.vacancyIndustry ? inSido(store.vacancyIndustry.rows, selection.sido) : [];
  const sidoInsuredIndustry = store.insuredIndustry ? inSido(store.insuredIndustry.rows, selection.sido) : [];

  // 카드 10 — 산업 대분류별 유효구인 (감춤: 시도에 vacancyIndustry 행이
  // 하나도 없을 때). 대상이 없는 카드라 축 이름으로 시작한다(화면 규칙 2).
  // 배지·본문 모두 vacancyIndustry 를 쓴다 — store.vacancy(직종 축)는 절대
  // 안 읽는다. mult 는 넣지 않는다: 구인배수는 구직이 있어야 하는데 이
  // 탭엔 구직 자체가 없다(요구사항 4).
  if (hasValue(sidoVacancyIndustry, {})) {
    const byIndustry = new Map();
    for (const r of sidoVacancyIndustry) {
      if (!r.industry) continue; // est 의 "전체 합계" 류 빈 문자열 행은 랭킹에서 뺀다.
      const cur = byIndustry.get(r.industry) ?? { vacancy: 0 };
      cur.vacancy += r.vacancy ?? 0;
      byIndustry.set(r.industry, cur);
    }
    const items = [...byIndustry.entries()]
      .sort((a, b) => b[1].vacancy - a[1].vacancy)
      .slice(0, 8)
      .map(([industry, sums]) => ({
        label: industry,
        value: sums.vacancy,
        highlighted: industry === name,
      }));

    cards.push(card({
      title: '<span class="pin">10</span>산업 대분류별 유효구인',
      badge: period(store.vacancyIndustry.period),
      body: bars({ items }),
    }));
  }

  // 카드 11 — 〈선택업종〉 피보험자 (감춤: 선택 업종 행이 이 시도에 없을
  // 때). 직종별 화면 카드 8과 같은 표(스펙 §4.3)라 본문은 공용 부품
  // components.insuredBody 를 그대로 부른다 — 다시 만들지 않는다. 이
  // 화면이 맡는 건 "이 축(산업)에서 선택 업종 행 찾기"뿐이다.
  const industryInsured = sidoInsuredIndustry.filter((r) => r.industry === name);
  if (hasValue(sidoInsuredIndustry, { industry: name })) {
    const insuredSum = sumBy(industryInsured, "insured");
    const gainedSum = sumBy(industryInsured, "gained");
    const lostSum = sumBy(industryInsured, "lost");

    // 전년동월대비(R32) — store.insuredSeries 는 지금 sido 단위까지만
    // 쌓이고 industry 축이 없다(occupation 축과 마찬가지 사정, 직종별
    // 화면 카드 8 주석 참고). find 는 industry 까지 요구해 두되 지금
    // 수집되는 행에는 그 필드가 없어 실제로는 항상 못 찾는다 — 줄만
    // 조용히 빠지고 카드는 죽지 않는다.
    const priorRow = store.insuredSeries?.rows?.find((r) =>
      r.sido === selection.sido && r.industry === name);

    cards.push(card({
      title: `<span class="pin">11</span>${esc(titleFor(name, "피보험자"))}`,
      badge: period(store.insuredIndustry.period),
      badgeClass: "badge--jh",
      body: insuredBody({ insured: insuredSum, gained: gainedSum, lost: lostSum,
                          priorInsured: priorRow?.insured }),
    }));
  }

  // 카드 12 — 〈선택업종〉 경력직 이동 (감춤: 맞는 mobility 행이 없을 때).
  // mobility 는 시도 축 그 자체다(Task 9c 가 행정표준코드로 고쳤다) —
  // row.sido === sido 로 거른다. 위 카드 10·11 의 inSido()(sigungu 접두)와
  // 절대 섞지 않는다(R35). 산업 축은 대분류뿐이라(수집 컬럼이
  // "산업(이전)_대분류" 하나) 중분류로 내려가는 계층은 없다.
  const industryMobility = store.mobility.rows.filter((r) =>
    r.sido === selection.sido && r.industry === name);
  if (hasValue(store.mobility.rows, { sido: selection.sido, industry: name })) {
    const items = [...industryMobility]
      .sort((a, b) => b.movers - a.movers)
      .slice(0, 5)
      .map((r) => ({ label: r.prev_industry, value: r.movers }));

    cards.push(card({
      title: `<span class="pin">12</span>${esc(titleFor(name, "경력직 이동"))}`,
      badge: period(store.mobility.period),
      badgeClass: "badge--jh",
      body: `<div class="subhead">유입 경력직의 <b>이전 업종</b></div>
        ${bars({ items, variant: "jh" })}`,
    }));
  }

  // 카드 13 — 〈선택업종〉 채용인원 (감춤: 맞는 est 행이 없을 때). 값
  // 하나뿐이라 접지 않는다(collapseCard 아니라 card, 요구사항이 명시).
  // est 는 산업 코드를 industry 에, 이름을 industry_name 에 담는다 —
  // 조인은 industry_name 으로 한다(R33), 산업 코드 사전을 만들지 않는다.
  const hiredSelection = { sido: selection.sido, size: "전규모", industry_name: name, item: "채용인원" };
  if (hasValue(store.est.rows, hiredSelection)) {
    const hired = store.est.rows.find((r) =>
      r.sido === hiredSelection.sido && r.size === hiredSelection.size &&
      r.industry_name === hiredSelection.industry_name && r.item === hiredSelection.item);
    cards.push(card({
      title: `<span class="pin">13</span>${esc(titleFor(name, "채용인원"))}`,
      badge: half(store.est.period),
      badgeClass: "badge--est",
      body: `<div class="card__value num">${num(hired.value)}<small>명</small></div>`,
    }));
  }

  return `<div class="cards">${cards.join("")}</div>`;
}
