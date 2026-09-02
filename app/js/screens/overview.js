import { card, pairCard, num, RATIO_NOTE } from "../components.js";
import { ratio } from "../data.js";

// 총괄 화면 — 스펙 §4.1. 시도 단위(R4)로 거른다: store.vacancy/placement/insured
// 는 data.js 가 이미 *_sido.json 을 읽어 채워 둔다(app/js/data.js FILE_OF 참고).
// 화면 규칙 1 — 값이 없으면 카드째 감춘다. 전국 값 대체도, 빈칸도 없다.
// 추세 카드(스펙 §4.1 카드 2)는 24개월 시계열이 필요한데, 이 파이프라인은
// 매번 최신 한 시점만 받아 쓰고 이력을 쌓지 않는다(pipeline/collect.py — 매
// 수집이 data/*.json 을 그대로 덮어쓴다). 없는 이력을 지어내 그리면 화면
// 규칙 1을 정면으로 어기므로, components.trend 는 구현·검증만 해 두고(R8)
// 이 화면에는 아직 배선하지 않는다 — 목업도 이 카드 값을 "예시" 로 표시해
// 두었다("인용하실 값이 아닙니다").
const period = (p) => p.replace(/(\d{4})(\d{2})/, "$1.$2");
const half = (p) => `’${p.slice(2, 4)} ${p.slice(4) === "01" ? "상반기" : "하반기"}`;

export function render(store, selection = { sido: "11" }) {
  const v = store.vacancy.rows.find((r) => r.sido === selection.sido);
  const pl = store.placement.rows.find((r) => r.sido === selection.sido);
  const ins = store.insured.rows.find((r) => r.sido === selection.sido);
  const plan = store.est.rows.find((r) =>
    r.sido === selection.sido && r.size === "전규모" &&
    r.occupation === "" && r.item === "채용계획인원");

  const cards = [];

  if (v && v.vacancy != null && v.seekers != null) {
    cards.push(card({
      title: '<span class="pin">1</span>유효구인 · 유효구직',
      badge: period(store.vacancy.period),
      body: pairCard({ vacancy: v.vacancy, seekers: v.seekers,
                       ratio: ratio(v.vacancy, v.seekers) }),
      notes: [RATIO_NOTE],
    }));
  }

  if (pl && pl.placements != null) {
    cards.push(card({
      title: '<span class="pin">3</span>취업건수',
      badge: period(store.placement.period),
      body: `<div class="card__value num">${num(pl.placements)}<small>건</small></div>`,
      notes: ["그 달 <b>알선·본인 취업으로 마감된</b> 건수"],
    }));
  }

  if (ins && ins.insured != null) {
    const net = (ins.gained ?? 0) - (ins.lost ?? 0);
    const netLabel = `${net > 0 ? "+" : ""}${num(net)}`;
    cards.push(card({
      title: '<span class="pin">4</span>고용보험 피보험자',
      badge: period(store.insured.period),
      body: `<div class="card__value num">${num(ins.insured)}<small>명</small></div>
        <dl class="trio">
          <div><dt>취득</dt><dd class="num">${num(ins.gained)}</dd></div>
          <div><dt>상실</dt><dd class="num">${num(ins.lost)}</dd></div>
          <div><dt>순증</dt><dd class="num">${netLabel}</dd></div>
        </dl>`,
      notes: ["<b>사업장 소재지</b> 기준"],
    }));
  }

  // 값이 없으면 카드째 감춘다 — 빈칸도, 전국 값 대체도 하지 않는다.
  if (plan) {
    cards.push(card({
      title: '<span class="pin">5</span>채용계획인원',
      badge: half(store.est.period),
      badgeClass: "badge--est",
      body: `<div class="card__value num">${num(plan.value)}<small>명</small></div>`,
    }));
  }

  return `<div class="cards">${cards.join("")}</div>`;
}
