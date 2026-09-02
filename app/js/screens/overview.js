import { card, pairCard, trend, num, esc, RATIO_NOTE, insuredBody } from "../components.js";
import { ratio, hasValue, period, half, priorYearPeriod } from "../data.js";
import { SIDO_OF_SCOPE } from "../tilemap.js";

// 총괄 화면 — 스펙 §4.1. 시도 단위(R4)로 거른다: store.vacancySido/
// placementSido/insuredSido 를 읽는다 — store.vacancy/placement/insured
// (시군구 원자료)는 절대 읽지 않는다(R20 — 헷갈리면 에러 없이 축만 틀리게
// 그려진다, 이 프로젝트에서 가장 나쁜 실패 모양).
// 화면 규칙 1 — 값이 없으면 카드째 감춘다. 전국 값 대체도, 빈칸도 없다.
// 판단은 전부 data.js 의 hasValue() 하나로 한다(카드 감춤 규칙의 단일
// 판단점) — 화면마다 각자 find()/조건문을 다시 짜지 않는다.
// 추세(카드 2)·전년동월대비(카드 4)는 store.vacancySeries/insuredSeries
// (Task 9b가 낸 마감년월 축 시계열, R19/R27)를 읽는다. data.load() 가 이
// 파일들을 선택적으로 싣기 때문에(R31) 수집이 아직 없으면 undefined 이고,
// 그 경우도 hasValue 가 카드를 감춘다 — 없는 이력을 지어내지 않는다.
// period/half 는 직종별 화면(Task 12)도 그대로 쓰므로 data.js 로 올렸다 —
// 화면마다 복사하지 않는다.

export function render(store, selection = { sido: "11" }) {
  const bySido = { sido: selection.sido };
  // I1 실측 (2026-09-02, KOSIS 실호출) — "전직종" 행의 코드는 접두만 있는
  // `keco2026_` 이고, est.collect 가 접두를 떼므로 occupation 은 정확히 ""다
  // (서울·전규모·202601 채용계획인원 109,560). **산업 쪽은 다르다** —
  // "전산업"은 `2026INDUSTRY_11S000` 이라 뒤가 비어 있지 않다. 이 비대칭을
  // 유추로 뒤집지 마라: tests/test_est.py 가 두 축을 각각 못 박아 뒀다.
  const planSelection = { sido: selection.sido, size: "전규모", occupation: "", item: "채용계획인원" };

  const cards = [];

  if (hasValue(store.vacancySido.rows, bySido)) {
    const v = store.vacancySido.rows.find((r) => r.sido === selection.sido);
    if (v.vacancy != null && v.seekers != null) {
      cards.push(card({
        title: '<span class="pin">1</span>유효구인 · 유효구직',
        badge: period(store.vacancySido.period),
        body: pairCard({ vacancy: v.vacancy, seekers: v.seekers,
                         ratio: ratio(v.vacancy, v.seekers) }),
        notes: [RATIO_NOTE],
      }));
    }
  }

  // 카드 2 — 24개월 추세. store.vacancySeries 가 없거나 이 시도 행이 하나도
  // 없으면 카드째 감춘다(hasValue). 값을 지어내 그리지 않는다.
  if (hasValue(store.vacancySeries?.rows, bySido)) {
    const seriesRows = store.vacancySeries.rows
      .filter((r) => r.sido === selection.sido)
      .sort((a, b) => a.period.localeCompare(b.period));
    const labels = seriesRows.map((r) => period(r.period));
    cards.push(card({
      title: '<span class="pin">2</span>유효구인 · 유효구직 추세',
      badge: `${labels[0]}~${labels[labels.length - 1]}`,
      body: trend({
        series: [
          { name: "유효구인", values: seriesRows.map((r) => r.vacancy), color: "#1baf7a", unit: "명" },
          { name: "유효구직", values: seriesRows.map((r) => r.seekers), color: "#2a78d6", unit: "건" },
        ],
        labels,
      }),
    }));
  }

  // 수도권 비교 (표) — 스펙 §4.1 이 카드 2 뒤·카드 3 앞에 그린 자리다(핀 번호가
  // 없는 유일한 카드라 제목에도 .pin 을 붙이지 않는다). 시도 셋을 한눈에 견주는
  // 것이 이 대시보드의 이름값("수도권")이고, 스위처로 시도를 갈아 보며 비교하는
  // 수고를 없앤다. 값은 이미 실린 store.vacancySido 세 줄이 전부다 — 새 자료를
  // 받지 않는다.
  //
  // 지역 이름표는 tilemap.SIDO_OF_SCOPE 하나에서 뒤집어 만든다. 서울 11 · 경기
  // 41 · 인천 28 은 이 프로젝트가 한 번 틀렸던 값이라(R9 — 경기를 KOSIS 코드
  // 31 로 적었다) 사본을 늘리지 않는다.
  const metroRows = Object.entries(SIDO_OF_SCOPE)
    .map(([label, code]) => ({ label, code, row: store.vacancySido.rows.find((r) => r.sido === code) }))
    .filter((entry) => entry.row);
  if (metroRows.length) {
    // 없는 시도는 줄을 지어내지 않고 그냥 빠진다 — 화면 규칙 1 의 표 안 판본이다.
    const bodyRows = metroRows.map(({ label, code, row }) => {
      const isMe = code === selection.sido ? ' class="is-me"' : "";
      return `<tr${isMe}><td>${esc(label)}</td>
        <td class="num">${num(row.vacancy)}</td>
        <td class="num">${num(row.seekers)}</td>
        <td class="num">${ratio(row.vacancy, row.seekers) ?? "—"}</td></tr>`;
    }).join("");
    cards.push(card({
      title: "수도권 비교",
      badge: period(store.vacancySido.period),
      body: `<table class="tbl">
        <thead><tr><th>지역</th><th>유효구인</th><th>유효구직</th><th>구인배수</th></tr></thead>
        <tbody>${bodyRows}</tbody>
      </table>`,
      notes: [RATIO_NOTE],
    }));
  }

  if (hasValue(store.placementSido.rows, bySido)) {
    const pl = store.placementSido.rows.find((r) => r.sido === selection.sido);
    if (pl.placements != null) {
      cards.push(card({
        title: '<span class="pin">3</span>취업건수',
        badge: period(store.placementSido.period),
        body: `<div class="card__value num">${num(pl.placements)}<small>건</small></div>`,
        notes: ["그 달 <b>알선·본인 취업으로 마감된</b> 건수"],
      }));
    }
  }

  if (hasValue(store.insuredSido.rows, bySido)) {
    const ins = store.insuredSido.rows.find((r) => r.sido === selection.sido);
    if (ins.insured != null) {
      // 전년동월대비(R32) — 직종 축 시계열이 없어 이번 판은 시도 단위
      // 카드 4에만 붙인다. 같은 sido·12개월 전 같은 달 행이 있을 때만
      // 붙이고, 없으면 그 줄만 뺀다(전월대비는 요구에서 명시적으로 뺐다).
      // 델타 계산·trio 마크업 자체는 components.insuredBody 가 한다 —
      // 여기는 "이 축(시도)에서 1년 전 같은 달 행 찾기"만 담당한다.
      const priorPeriod = priorYearPeriod(store.insuredSido.period);
      const priorRow = store.insuredSeries?.rows?.find((r) =>
        r.sido === selection.sido && r.period === priorPeriod);

      cards.push(card({
        title: '<span class="pin">4</span>고용보험 피보험자',
        badge: period(store.insuredSido.period),
        body: insuredBody({ insured: ins.insured, gained: ins.gained, lost: ins.lost,
                            priorInsured: priorRow?.insured }),
        notes: ["<b>사업장 소재지</b> 기준"],
      }));
    }
  }

  // 값이 없으면 카드째 감춘다 — 빈칸도, 전국 값 대체도 하지 않는다.
  // (직종 소분류를 고르면 이 selection 에 맞는 행이 없어 카드가 사라진다 — Task 12.)
  if (hasValue(store.est.rows, planSelection)) {
    const plan = store.est.rows.find((r) =>
      r.sido === planSelection.sido && r.size === planSelection.size &&
      r.occupation === planSelection.occupation && r.item === planSelection.item);
    cards.push(card({
      title: '<span class="pin">5</span>채용계획인원',
      badge: half(store.est.period),
      badgeClass: "badge--est",
      body: `<div class="card__value num">${num(plan.value)}<small>명</small></div>`,
    }));
  }

  return `<div class="cards">${cards.join("")}</div>`;
}
