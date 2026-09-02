import { card, pairCard, trend, num, RATIO_NOTE } from "../components.js";
import { ratio, hasValue } from "../data.js";

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
const period = (p) => p.replace(/(\d{4})(\d{2})/, "$1.$2");
const half = (p) => `’${p.slice(2, 4)} ${p.slice(4) === "01" ? "상반기" : "하반기"}`;

export function render(store, selection = { sido: "11" }) {
  const bySido = { sido: selection.sido };
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
      const net = (ins.gained ?? 0) - (ins.lost ?? 0);
      const netLabel = `${net > 0 ? "+" : ""}${num(net)}`;

      // 전년동월대비(R32) — 직종 축 시계열이 없어 이번 판은 시도 단위
      // 카드 4에만 붙인다. 같은 sido·12개월 전 같은 달 행이 있을 때만
      // 붙이고, 없으면 그 줄만 뺀다(전월대비는 요구에서 명시적으로 뺐다).
      const priorPeriod = String(Number(store.insuredSido.period.slice(0, 4)) - 1)
        + store.insuredSido.period.slice(4);
      const priorRow = store.insuredSeries?.rows?.find((r) =>
        r.sido === selection.sido && r.period === priorPeriod);
      let deltaRow = "";
      if (priorRow) {
        const delta = ins.insured - priorRow.insured;
        const cls = delta >= 0 ? "is-up" : "is-down";
        const arrow = delta >= 0 ? "▲" : "▼";
        deltaRow = `<div class="deltarow"><span class="card__delta ${cls}">${arrow} ${num(Math.abs(delta))}<small>전년동월대비</small></span></div>`;
      }

      cards.push(card({
        title: '<span class="pin">4</span>고용보험 피보험자',
        badge: period(store.insuredSido.period),
        body: `<div class="card__value num">${num(ins.insured)}<small>명</small></div>
          ${deltaRow}
          <dl class="trio">
            <div><dt>취득</dt><dd class="num">${num(ins.gained)}</dd></div>
            <div><dt>상실</dt><dd class="num">${num(ins.lost)}</dd></div>
            <div><dt>순증</dt><dd class="num">${netLabel}</dd></div>
          </dl>`,
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
