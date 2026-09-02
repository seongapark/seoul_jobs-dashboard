export const num = (value) => value == null ? "—" : value.toLocaleString("ko-KR");

// 화면 규칙 5 — 구인배수를 보여주는 카드에는 이 각주가 반드시 붙는다.
export const RATIO_NOTE = "구인배수 &lt; 1 : 일자리 부족";

export function card({ title, badge, badgeClass = "badge--jo", body, notes = [] }) {
  const noteHtml = notes.length
    ? `<ul class="bul">${notes.map((n) => `<li>${n}</li>`).join("")}</ul>`
    : "";
  return `<div class="card">
    <div class="card__head">
      <div class="card__name">${title}</div>
      ${badge ? `<span class="badge ${badgeClass}">${badge}</span>` : ""}
    </div>
    ${body}${noteHtml}
  </div>`;
}

// 유효구인·유효구직 두 칸 + 구인배수(+취업건수). 화면 규칙 4 — 막대/칸에 값을
// 직접 단다. dot 은 목업의 pane__lab 표기를 그대로 옮긴 것.
export function pairCard({ vacancy, seekers, ratio, placements }) {
  return `<div class="pair">
    <div class="pane pane--jo">
      <div class="pane__lab"><i class="dot dot--jo"></i>유효구인인원</div>
      <div class="pane__val num">${num(vacancy)}<small>명</small></div>
    </div>
    <div class="pane pane--jh">
      <div class="pane__lab"><i class="dot dot--jh"></i>유효구직건수</div>
      <div class="pane__val num">${num(seekers)}<small>건</small></div>
    </div>
  </div>
  <div class="pairfoot">
    <span>구인배수 <b class="num">${ratio ?? "—"}</b></span>
    ${placements != null ? `<span>취업 <b class="num">${num(placements)}</b>건</span>` : ""}
  </div>`;
}

const TREND_W = 320;
const TREND_H = 104;
const PAD = 8;

// 추세 카드(스펙 §4.1 카드 2, R8) — 두 계열을 한 축에 그리는 최소 인라인 SVG.
// 두 계열의 값을 함께 min/max 로 스케일해 y 좌표를 만든다: 두 계열이 같은
// 눈금을 공유하므로 y축이 하나뿐이다(두 계열마다 다른 축을 쓰지 않는다).
export function trend({ series, labels }) {
  const values = series.flatMap((s) => s.values);
  const max = Math.max(...values, 0);
  const min = Math.min(...values, 0);
  const span = max - min || 1;
  const n = Math.max(...series.map((s) => s.values.length), 1);

  const x = (i) => PAD + (i * (TREND_W - PAD * 2)) / Math.max(1, n - 1);
  const y = (v) => TREND_H - PAD - ((v - min) / span) * (TREND_H - PAD * 2);

  const gridLines = [0.25, 0.5, 0.75]
    .map((f) => {
      const gy = (TREND_H - PAD - f * (TREND_H - PAD * 2)).toFixed(1);
      return `<line x1="${PAD - 4}" y1="${gy}" x2="${TREND_W - PAD + 4}" y2="${gy}" stroke="#eef0f3" stroke-width="1"></line>`;
    })
    .join("");
  const baseline = `<line x1="${PAD - 4}" y1="${(TREND_H - PAD).toFixed(1)}" x2="${TREND_W - PAD + 4}" y2="${(TREND_H - PAD).toFixed(1)}" stroke="#e2e5ea" stroke-width="1"></line>`;

  const lines = series
    .map((s) => {
      const points = s.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
      const lastI = s.values.length - 1;
      const lx = x(lastI);
      const ly = y(s.values[lastI]);
      return `<polyline fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" points="${points}"></polyline>
      <circle cx="${lx.toFixed(1)}" cy="${ly.toFixed(1)}" r="3.5" fill="${s.color}" stroke="#fff" stroke-width="2"></circle>
      <text x="${(lx - 4).toFixed(1)}" y="${(ly - 6).toFixed(1)}" text-anchor="end" font-size="9" font-weight="700" fill="${s.color}">${num(s.values[lastI])}</text>`;
    })
    .join("");

  const legend = series
    .map((s) => `<span><i class="dot" style="background:${s.color}"></i>${s.name}(${s.unit ?? "명"})</span>`)
    .join("");

  const period = labels && labels.length ? `${labels[0]}~${labels[labels.length - 1]}` : "";
  const ariaLabel = `${series.map((s) => s.name).join(" · ")} 추세${period ? ` (${period})` : ""}`;

  return `<svg class="trend" viewBox="0 0 ${TREND_W} ${TREND_H}" role="img" aria-label="${ariaLabel}">
    ${baseline}
    ${gridLines}
    ${lines}
  </svg>
  <div class="legend">${legend}</div>`;
}
