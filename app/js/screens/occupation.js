import { card, pairCard, bars, collapseCard, esc, num, RATIO_NOTE, insuredBody } from "../components.js";
import { ratio, hasValue, titleFor, period, half, inSido, sumBy, shortSigunguName } from "../data.js";

// 직종별 화면 — 컨트롤러가 다시 쓴 브리프(task-12-brief.md) §전체가 유일한
// 요구사항이다. 플랜 원문의 카드 3장 스케치는 실데이터 모양과 어긋나(R21~26)
// 폐기됐다.
//
// overview 와 결정적으로 다른 점 하나: 이 화면은 시군구 원자료
// (store.vacancy/placement/insured)를 직접 읽는다 — 시도 집계 파일이 없다.
// 그래서 지역 필터를 화면이 직접 건다: 시군구 행에는 sido 필드가 없고
// sigungu 코드(행정표준코드)의 앞 두 자리가 시도다(서울 11·경기 41·인천 28).
// row.sido === sido 로 잘못 쓰면 시군구 행 전부가 필터를 통과 못 해
// 카드가 조용히 다 사라진다(R22) — inSido()/sumBy() 는 산업별 화면
// (Task 13)도 그대로 쓰므로 data.js 로 올렸다(화면마다 복사하지 않는다).

// 카드 감춤 규칙(화면 규칙 1)의 단일 판단점은 여전히 data.hasValue() 다.
// hasValue(rows, {}) 는 selection 이 빈 객체라 모든 행에 대해 vacuously
// true 라 rows.length > 0 과 같다 — "이 시도에 행이 하나라도 있는가"도
// 같은 함수 하나로 판단해 화면마다 별도 존재-체크를 다시 짜지 않는다.

// shortSigunguName 은 data.js 로 올라갔다(센터별 화면(Task 14)도 똑같이
// 필요해져 공용 자리로 옮김) — 화면마다 복사하지 않는다.

export function render(store, selection) {
  const name = selection.occupation;
  const cards = [];

  const sidoVacancy = inSido(store.vacancy.rows, selection.sido);
  const sidoPlacement = inSido(store.placement.rows, selection.sido);
  const sidoInsured = inSido(store.insured.rows, selection.sido);

  // 카드 6 — 직종별 유효구인 · 구인배수 (감춤: 시도에 행이 하나도 없을 때).
  // 대상이 없는 카드라 축 이름으로 시작한다(화면 규칙 2).
  if (hasValue(sidoVacancy, {})) {
    const byOcc = new Map();
    for (const r of sidoVacancy) {
      const cur = byOcc.get(r.occupation) ?? { vacancy: 0, seekers: 0 };
      cur.vacancy += r.vacancy ?? 0;
      cur.seekers += r.seekers ?? 0;
      byOcc.set(r.occupation, cur);
    }
    const items = [...byOcc.entries()]
      .sort((a, b) => b[1].vacancy - a[1].vacancy)
      .slice(0, 10)
      .map(([occ, sums]) => ({
        label: occ,
        value: sums.vacancy,
        mult: ratio(sums.vacancy, sums.seekers) ?? "—",
        highlighted: occ === name,
      }));

    cards.push(card({
      title: '<span class="pin">6</span>직종별 유효구인',
      badge: period(store.vacancy.period),
      body: bars({ items }),
      notes: [RATIO_NOTE],
    }));
  }

  // 카드 7 — 〈선택직종〉 유효구인 · 유효구직 (감춤: 선택 직종 행이 이 시도에
  // 없을 때). 집계 규칙: 시도 안 시군구 행을 직종별로 합산한다 — "분해값을
  // 더해 총계로 쓰지 않는다"는 시도·전국 총계 카드에만 걸리고(R5), 이
  // 화면의 직종별 값에는 안 걸린다.
  const occVacancy = sidoVacancy.filter((r) => r.occupation === name);
  if (hasValue(sidoVacancy, { occupation: name })) {
    const vacancySum = sumBy(occVacancy, "vacancy");
    const seekersSum = sumBy(occVacancy, "seekers");

    const occPlacement = sidoPlacement.filter((r) => r.occupation === name);
    const placements = occPlacement.length ? sumBy(occPlacement, "placements") : null;

    const districtItems = [...occVacancy]
      .sort((a, b) => b.vacancy - a.vacancy)
      .slice(0, 8)
      .map((r) => ({
        label: shortSigunguName(store.sigunguNames, r.sigungu),
        value: r.vacancy,
      }));

    cards.push(card({
      title: `<span class="pin">7</span>${esc(titleFor(name))}`,
      badge: period(store.vacancy.period),
      body: `${pairCard({ vacancy: vacancySum, seekers: seekersSum,
                          ratio: ratio(vacancySum, seekersSum) ?? "—", placements })}
        <div class="subhead">자치구별 유효구인</div>
        ${bars({ items: districtItems })}`,
      notes: [RATIO_NOTE],
    }));
  }

  // 카드 8 — 〈선택직종〉 피보험자 (감춤: 선택 직종 행이 이 시도에 없을 때).
  // 각주 없음(요구에서 명시적으로 지웠다).
  const occInsured = sidoInsured.filter((r) => r.occupation === name);
  if (hasValue(sidoInsured, { occupation: name })) {
    const insuredSum = sumBy(occInsured, "insured");
    const gainedSum = sumBy(occInsured, "gained");
    const lostSum = sumBy(occInsured, "lost");

    // 전년동월대비(R32) — store.insuredSeries 는 지금 sido 단위까지만
    // 쌓이고 occupation 축이 없다(store shape 주석 참고). 그래서 아래
    // find 는 occupation 까지 함께 요구해 두되, 지금 수집되는 행에는 그
    // 필드가 없어 실제로는 항상 못 찾는다 — 조용히 줄이 빠질 뿐 카드는
    // 죽지 않는다. 나중에 직종 축 시계열이 생기면 이 화면을 고치지 않고
    // 그대로 살아나도록 미리 배선해 둔 것이다. 델타 계산·trio 마크업
    // 자체는 components.insuredBody 가 한다(overview 카드4와 공유) —
    // 여기는 "이 축(직종)에서 1년 전 같은 달 행 찾기"만 담당한다.
    const priorRow = store.insuredSeries?.rows?.find((r) =>
      r.sido === selection.sido && r.occupation === name);

    cards.push(card({
      title: `<span class="pin">8</span>${esc(titleFor(name, "피보험자"))}`,
      badge: period(store.insured.period),
      badgeClass: "badge--jh",
      body: insuredBody({ insured: insuredSum, gained: gainedSum, lost: lostSum,
                          priorInsured: priorRow?.insured }),
    }));
  }

  // 카드 9 — 〈선택직종〉 채용계획인원 (감춤: 맞는 est 행이 없을 때 — 예:
  // 소분류 선택). est 는 KECO 코드를 occupation 에, 이름을 occupation_name
  // 에 담는다 — 조인은 occupation_name 으로 한다(R33), occupation 코드
  // 사전을 만들지 않는다(R25).
  const planSelection = { sido: selection.sido, size: "전규모", occupation_name: name, item: "채용계획인원" };
  if (hasValue(store.est.rows, planSelection)) {
    const plan = store.est.rows.find((r) =>
      r.sido === planSelection.sido && r.size === planSelection.size &&
      r.occupation_name === planSelection.occupation_name && r.item === planSelection.item);
    cards.push(collapseCard({
      title: `<span class="pin">9</span>${esc(titleFor(name, "채용계획인원"))}`,
      badge: half(store.est.period),
      badgeClass: "badge--est",
      body: `<div class="card__value num">${num(plan.value)}<small>명</small></div>`,
    }));
  }

  return `<div class="cards">${cards.join("")}</div>`;
}
