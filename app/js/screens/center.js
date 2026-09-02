import { card, collapseCard, bars, esc, num, RATIO_NOTE } from "../components.js";
import { hasValue, ratio, titleFor, period, selectionHash } from "../data.js";
import { render as renderTiles } from "../tilemap.js";

// 센터별 화면 — 컨트롤러가 다시 쓴 브리프(task-14-brief.md) §전체가 유일한
// 요구사항이다. 플랜 원문의 Task 14는 카드 16(스펙 §4.4)이 통째로 빠져
// 있고 경기 시도 코드를 31(KOSIS 코드)로 잘못 적어 폐기됐다 — 41이 맞다
// (R9).
//
// 이 화면이 다른 셋과 결정적으로 다른 점: EIS 에 센터 축이 아예 없다
// (판정 R5). 그래서 "센터 합계"는 그 센터가 관할하는 시군구 값의 합으로
// 정의한다 — row.center 가 이미 센터 이름을 담고 있어 그대로 그룹 키로
// 쓴다("분해합으로 총계를 대체하지 않는다"는 시도·전국 총계에만 걸리고
// (R5), 센터 집계에는 안 걸린다). 그리고 이 라우트엔 직종/산업 스위처
// 자체가 없다(app.js 의 renderSwitcher 가 지역만 붙인다) — 그래서 카드
// 14·15·16 모두 selection.occupation/industry 를 전혀 읽지 않고 시군구
// 원자료 전체(모든 직종·산업)를 합산한다. 카드 16 만 별도로 그 이유가
// 명시돼 있지만(스펙 §4.4), 실은 이 화면 전체가 처음부터 그 축을 안 본다.

const SCOPE_CHIPS = ["수도권", "서울", "경기", "인천"];
const SIDO_OF_SCOPE = { 서울: "11", 경기: "41", 인천: "28" };
// 지도 램프 변수 접두와 legend 색 클래스(.ramp__nm.s/g/i, app.css)를 함께 문다.
const RAMP_OF_SCOPE = [
  { label: "서울", cls: "s", prefix: "s" },
  { label: "경기", cls: "g", prefix: "g" },
  { label: "인천", cls: "i", prefix: "i" },
];

// 센터 이름의 "고용센터" 접미를 뗀다(스펙 §4.4, 카드 15 라벨 규칙) —
// "서울고용센터" -> "서울", "인천서부고용센터" -> "인천서부".
function shortCenterName(center) {
  return center.endsWith("고용센터") ? center.slice(0, -4) : center;
}

// store.vacancy.rows(시군구 원자료, 모든 직종 포함)를 한 필드(시군구 또는
// 센터) 기준으로 유효구인·유효구직 합산한다. 이 화면의 카드 14·15가 똑같은
// 모양의 집계를 시군구 축/센터 축으로만 달리 해서, 한 번의 순회로 둘 다
// 만든다 — store.vacancy.rows 를 두 번 훑지 않는다.
function aggregate(rows) {
  const bySigungu = new Map();
  const byCenter = new Map();
  for (const r of rows) {
    const g = bySigungu.get(r.sigungu) ?? { vacancy: 0, seekers: 0 };
    g.vacancy += r.vacancy ?? 0;
    g.seekers += r.seekers ?? 0;
    bySigungu.set(r.sigungu, g);

    const c = byCenter.get(r.center) ?? { vacancy: 0, seekers: 0, sido: r.sigungu.slice(0, 2) };
    c.vacancy += r.vacancy ?? 0;
    c.seekers += r.seekers ?? 0;
    byCenter.set(r.center, c);
  }
  return { bySigungu, byCenter };
}

export function render(store, selection) {
  const cards = [];
  const scopeSido = SIDO_OF_SCOPE[selection.scope];
  const { bySigungu, byCenter } = aggregate(store.vacancy.rows);

  // 타일 코드 -> 센터 이름. 지도에서 시군구를 고르면 그 센터도 함께
  // 골라지도록(카드 16이 selection.center 를 읽는다) 타일 한 번 순회로
  // 만들어 둔다 — 시군구 코드로 store.vacancy.rows 를 매번 find() 하지
  // 않는다.
  const centerOfSigungu = new Map();
  for (const r of store.vacancy.rows) {
    if (!centerOfSigungu.has(r.sigungu)) centerOfSigungu.set(r.sigungu, r.center);
  }

  // 카드 14 — 구인배수 지도 (감춤: vacancy 행이 없을 때). 대상이 없는
  // 카드가 아니라 지도 자체가 대상이라 화면 규칙 2 그대로 "구인배수
  // 지도"로 시작한다.
  if (hasValue(store.vacancy.rows, {})) {
    const values = {};
    for (const [code, sums] of bySigungu) {
      const r = ratio(sums.vacancy, sums.seekers);
      // ratio() 가 null 이면(분모 0) 이 코드는 그냥 안 실어 tilemap 이
      // "값 없음" 회색으로 그리게 둔다 — 0단계를 지어내지 않는다.
      if (r != null) values[code] = r;
    }

    const chips = SCOPE_CHIPS.map((label) => {
      const on = label === selection.scope ? " chip--on" : "";
      const nav = selectionHash({ ...selection, scope: label });
      return `<span class="chip${on}" role="button" tabindex="0" data-nav="${esc(nav)}">${esc(label)}</span>`;
    }).join("");

    const mapHtml = renderTiles(values, store.tileLayout, {
      selected: selection.sigungu,
      scope: selection.scope,
      navOf: (code) => selectionHash({ ...selection, sigungu: code, center: centerOfSigungu.get(code) }),
    });

    let selHtml;
    const tile = selection.sigungu ? store.tileLayout[selection.sigungu] : undefined;
    if (tile) {
      const sums = bySigungu.get(selection.sigungu) ?? { vacancy: 0, seekers: 0 };
      const centerName = centerOfSigungu.get(selection.sigungu);
      selHtml = `<div class="mapsel">
        <div class="mapsel__head">
          <span class="gu">${esc(tile.name)}</span>
          ${centerName ? `<span class="sub">› ${esc(centerName)}</span>` : ""}
        </div>
        <dl class="mapsel__stats">
          <div><dt>유효구인</dt><dd class="num">${num(sums.vacancy)}<small>명</small></dd></div>
          <div><dt>유효구직</dt><dd class="num">${num(sums.seekers)}<small>건</small></dd></div>
          <div><dt>구인배수</dt><dd class="num">${ratio(sums.vacancy, sums.seekers) ?? "—"}</dd></div>
        </dl>
      </div>`;
    } else {
      selHtml = `<div class="mapsel">타일을 눌러 시군구를 선택하세요</div>`;
    }

    const legendHtml = RAMP_OF_SCOPE.map(({ label, cls, prefix }) => `
      <div class="ramp">
        <div class="ramp__nm ${cls}">${label}</div>
        <div class="ramp__row">${[1, 2, 3, 4, 5].map((n) => `<i style="background:var(--${prefix}${n})"></i>`).join("")}</div>
        <div class="ramp__ends"><span>낮음</span><span>높음</span></div>
      </div>`).join("");

    cards.push(card({
      title: '<span class="pin">14</span>구인배수 지도',
      badge: period(store.vacancy.period),
      body: `<div class="chips">${chips}</div>
        ${mapHtml}
        ${selHtml}
        <div class="maplegend">${legendHtml}</div>`,
      notes: [RATIO_NOTE],
    }));
  }

  // 카드 15 — 센터별 구인 · 구직 (감춤: 센터 행이 없을 때 — vacancy 행이
  // 있으면 항상 row.center 도 있으므로 카드 14와 같은 조건이다).
  if (hasValue(store.vacancy.rows, {})) {
    const selectedCenter = selection.sigungu ? centerOfSigungu.get(selection.sigungu) : undefined;

    const items = [...byCenter.entries()]
      .filter(([, v]) => !scopeSido || v.sido === scopeSido)
      .sort((a, b) => b[1].vacancy - a[1].vacancy)
      .slice(0, 8);

    // 좌우가 같은 눈금 — 두 계열(유효구인·유효구직)을 통틀어 최댓값 하나로
    // 폭을 잰다. 각자 자기 계열의 최댓값으로 따로 재면 "구인이 구직만큼
    // 있다"는 거짓 인상을 준다(막대 길이가 서로 다른 기준이 되므로).
    const max = Math.max(...items.flatMap(([, v]) => [v.vacancy, v.seekers]), 0);
    const pct = (v) => (max > 0 ? Math.round((v / max) * 1000) / 10 : 0);

    const rows = items.map(([center, v]) => {
      const isSel = center === selectedCenter;
      return `<div class="bf__l"><span class="bf__n">${num(v.vacancy)}</span><i style="width:${pct(v.vacancy)}%"></i></div>
        <div class="bf__c${isSel ? " is-sel" : ""}">${esc(shortCenterName(center))}</div>
        <div class="bf__r"><i style="width:${pct(v.seekers)}%"></i><span class="bf__n">${num(v.seekers)}</span></div>`;
    }).join("");

    cards.push(card({
      title: '<span class="pin">15</span>센터별 구인 · 구직',
      badge: period(store.vacancy.period),
      body: `<div class="bf">
        <div class="bf__head l">유효구인</div>
        <div class="bf__head">센터</div>
        <div class="bf__head r">유효구직</div>
        ${rows}
      </div>`,
    }));
  }

  // 카드 16 — 〈선택센터〉 상위 산업 · 직종 (감춤: 선택 센터가 없을 때).
  // selection.occupation/selection.industry 를 절대 읽지 않는다(스펙 §4.4
  // 가 명시) — 스위처가 있는 다른 화면과 달리 이 카드는 "그 센터 전체"를
  // 본다. 애초에 이 라우트엔 그 스위처 UI 자체가 없다.
  if (selection.center) {
    const centerName = selection.center;

    // 상위 산업 — store.vacancyIndustry(산업 축은 직종 축과 다른 그리드라
    // 파일이 따로다). 이 키가 아직 안 실렸으면(15a 배선 전) 이 절만 뺀다.
    let industrySection = "";
    if (store.vacancyIndustry) {
      const byIndustry = new Map();
      for (const r of store.vacancyIndustry.rows) {
        if (r.center !== centerName || !r.industry) continue;
        byIndustry.set(r.industry, (byIndustry.get(r.industry) ?? 0) + (r.vacancy ?? 0));
      }
      const items = [...byIndustry.entries()]
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([label, value]) => ({ label, value }));
      if (items.length) {
        industrySection = `<div class="subhead">상위 산업</div>${bars({ items })}`;
      }
    }

    // 상위 직종 — store.vacancy(직종 축 그리드)를 센터로만 걸러 occupation
    // 으로 합산한다. store.vacancy 는 필수 파일이라 항상 있다.
    const byOccupation = new Map();
    for (const r of store.vacancy.rows) {
      if (r.center !== centerName || !r.occupation) continue;
      byOccupation.set(r.occupation, (byOccupation.get(r.occupation) ?? 0) + (r.vacancy ?? 0));
    }
    const occupationItems = [...byOccupation.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([label, value]) => ({ label, value }));
    const occupationSection = `<div class="subhead">상위 직종</div>${bars({ items: occupationItems })}`;

    cards.push(collapseCard({
      title: `<span class="pin">16</span>${esc(titleFor(centerName, "상위 산업 · 직종"))}`,
      badge: period(store.vacancy.period),
      body: `${industrySection}${occupationSection}`,
    }));
  }

  return `<div class="cards">${cards.join("")}</div>`;
}
