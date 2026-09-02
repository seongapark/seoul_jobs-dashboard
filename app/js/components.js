export const num = (value) => value == null ? "—" : value.toLocaleString("ko-KR");

// 화면 규칙 5 — 구인배수를 보여주는 카드에는 이 각주가 반드시 붙는다.
export const RATIO_NOTE = "구인배수 &lt; 1 : 일자리 부족";

const ESC_MAP = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

// R24 — 직종·산업·센터·시군구 이름은 데이터에서 그대로 와서 템플릿 문자열에
// 꽂힌다. esc 는 그 값에만 건다 — RATIO_NOTE 처럼 이미 완성된 HTML(엔티티
// 포함)을 다시 통과시키면 안 된다.
export function esc(text) {
  if (text == null) return "";
  return String(text).replace(/[&<>"']/g, (ch) => ESC_MAP[ch]);
}

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

const BAR_VARIANT_CLASS = { jo: "", jh: "bar--jh", est: "bar--est" };

// 가로 막대 랭킹(스펙 카드 6·10·12). 화면 규칙 4 — 값은 항상 막대에 직접
// 단다(bar__val) — 초록(구인)이 배경 대비 2.74:1 이라 색만으로는 못 읽는다.
export function bars({ items, variant = "jo" }) {
  const variantClass = BAR_VARIANT_CLASS[variant] ?? "";
  const max = Math.max(...items.map((it) => it.value), 0);
  const rows = items.map((it) => {
    // 최댓값을 100% 로 한 비율, 소수 첫째 자리. 최댓값이 0이면(전부 값 없음)
    // 나눗셈을 하지 않고 그냥 0%로 둔다.
    const pct = max > 0 ? Math.round((it.value / max) * 1000) / 10 : 0;
    const classes = ["bar", variantClass, it.highlighted ? "bar--hi" : "", it.sub ? "bar--sub" : ""]
      .filter(Boolean).join(" ");
    const mult = it.mult != null ? `<span class="bar__mult">×${it.mult}</span>` : "";
    return `<div class="${classes}">
      <div class="bar__lab">${esc(it.label)}${mult}</div>
      <div class="bar__val num">${num(it.value)}</div>
      <div class="bar__track" style="width:${pct}%"></div>
    </div>`;
  }).join("");
  return `<div class="bars">${rows}</div>`;
}

// 접히는 카드(스펙 카드 5·9·13·16). card() 와 인자 이름·badgeClass 기본값을
// 맞춰 두 컴포넌트를 헷갈리지 않고 바꿔 쓸 수 있게 한다.
export function collapseCard({ title, badge, badgeClass = "badge--jo", body }) {
  return `<details class="card">
    <summary>
      <div class="sumhead">
        <div class="sumname">${title}</div>
        ${badge ? `<span class="badge ${badgeClass}">${badge}</span>` : ""}
      </div>
      <div class="caretrow"><span class="caret">자세히 ▾</span></div>
    </summary>
    <div class="detail">${body}</div>
  </details>`;
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
