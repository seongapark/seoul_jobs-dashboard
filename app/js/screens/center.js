import { card, collapseCard, bars, esc, num, RATIO_NOTE } from "../components.js";
import { hasValue, ratio, titleFor, period, selectionHash, shortSigunguName } from "../data.js";
import { render as renderTiles, SIDO_OF_SCOPE } from "../tilemap.js";

// 센터별 화면 — 컨트롤러가 다시 쓴 브리프(task-14-brief.md) §전체가 유일한
// 요구사항이다. 플랜 원문의 Task 14는 카드 16(스펙 §4.4)이 통째로 빠져
// 있고 경기 시도 코드를 31(KOSIS 코드)로 잘못 적어 폐기됐다 — 41이 맞다
// (R9).
//
// 이 화면이 다른 셋과 결정적으로 다른 점: EIS 에 센터 축이 아예 없다
// (판정 R5). 그래서 "센터 합계"는 그 센터가 관할하는 시군구 값의 합으로
// 정의한다 — row.center 가 이미 센터 이름을 담고 있어 그대로 그룹 키로
// 쓴다("분해합으로 총계를 대체하지 않는다"는 시도·전국 총계에만 걸리고
// (R5), 센터 집계에는 안 걸린다).
//
// I5 — 스펙 §4.4 의 연동은 **두 층**이다:
//   1) 상단 스위처(직종) → 지도 색, 15번 막대 값
//   2) 지도 칩(scope)    → 지도 범위, 15번의 센터 목록
// 예전 구현은 1층이 통째로 없어 selection.occupation 을 아예 안 읽었고,
// 그래서 스펙이 그린 상담 시나리오("이 직종의 자리 사정을 구인배수 지도로")
// 가 성립하지 않았다. 직종을 안 고르면(첫 진입) 전체를 합산한다 — 그게
// "수도권 전체 자리 사정"이라는 자연스러운 기본값이다.
//
// **카드 16 만은 스위처를 따르지 않는다**(스펙이 명시). 그 카드는 "그 센터
// 전체의 상위 산업·직종"을 보는 것이라 축을 하나로 좁히면 의미가 없다 —
// 그래서 아래에서 걸러진 rows 가 아니라 store.vacancy.rows 원본을 쓴다.
//
// 산업 축은 이번 판에서 연동하지 않는다: 카드 14·15 의 값은 구인배수인데
// 스펙 §4.3 이 "구직은 산업 탭에 없다(유효구직에 산업 축 없음)"고 못 박아,
// 산업으로 좁힌 구인배수는 근거가 없다. 직종 축만 건다.

const SCOPE_CHIPS = ["수도권", "서울", "경기", "인천"];
// SIDO_OF_SCOPE 는 tilemap.js 가 갖고 여기가 import 한다(Task 16) — 사본을
// 둘로 늘리지 않는다.
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

  // I5 1층 — 카드 14·15 가 보는 행. 직종을 고르면 그 직종만, 안 고르면 전체.
  // 그 직종 행이 없는 시군구·센터는 집계에서 아예 빠진다 — 0 을 지어내
  // 그리면 지도가 "값이 0인 곳"과 "그 직종이 없는 곳"을 같은 색으로 만든다.
  const occupation = selection.occupation;
  const selectedRows = occupation
    ? store.vacancy.rows.filter((r) => r.occupation === occupation)
    : store.vacancy.rows;
  // 제목은 대상을 밝힌다(화면 규칙 2) — 안 그러면 걸러진 지도를 전체로 오독한다.
  const titleOf = (suffix) => occupation ? esc(titleFor(occupation, suffix)) : suffix;

  const { bySigungu, byCenter } = aggregate(selectedRows);

  // 타일 코드 -> 센터 이름. 지도에서 시군구를 고르면 그 센터도 함께
  // 골라지도록(카드 16이 selection.center 를 읽는다) 타일 한 번 순회로
  // 만들어 둔다 — 시군구 코드로 store.vacancy.rows 를 매번 find() 하지
  // 않는다. **여기는 걸러지지 않은 원본을 쓴다**(I5): 시군구→센터 관할은
  // 직종과 무관한 사실이라, 선택 직종 행이 없는 구를 눌렀다고 그 구의
  // 센터가 사라지면 안 된다.
  const centerOfSigungu = new Map();
  for (const r of store.vacancy.rows) {
    if (!centerOfSigungu.has(r.sigungu)) centerOfSigungu.set(r.sigungu, r.center);
  }

  // 카드 14 — 구인배수 지도 (감춤: 이 선택으로 남는 행이 없을 때). 직종을
  // 안 고르면 지도 자체가 대상이라 제목이 "구인배수 지도" 그대로이고, 고르면
  // 화면 규칙 2 대로 그 직종 이름으로 시작한다(titleOf).
  if (hasValue(selectedRows, {})) {
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
      // 구 이름은 tile_layout.json 의 name(파생 사본)이 아니라 정본인
      // store.sigunguNames 에서 뽑는다(브리프 명시, 리뷰 지적) — 배치
      // 파일을 손으로 손봐도 화면 이름이 정본과 갈리지 않게 한다.
      const guName = shortSigunguName(store.sigunguNames, selection.sigungu);
      selHtml = `<div class="mapsel">
        <div class="mapsel__head">
          <span class="gu">${esc(guName)}</span>
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
      title: `<span class="pin">14</span>${titleOf("구인배수 지도")}`,
      badge: period(store.vacancy.period),
      body: `<div class="chips">${chips}</div>
        ${mapHtml}
        ${selHtml}
        <div class="maplegend">${legendHtml}</div>`,
      notes: [RATIO_NOTE],
    }));
  }

  // 카드 15 — 센터별 구인 · 구직 (감춤: 센터 행이 없을 때 — vacancy 행이
  // 있으면 항상 row.center 도 있으므로 카드 14와 같은 조건이다). 카드 14 와
  // 같은 selectedRows 를 본다(I5 1층).
  if (hasValue(selectedRows, {})) {
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
      title: `<span class="pin">15</span>${titleOf("센터별 구인 · 구직")}`,
      badge: period(store.vacancy.period),
      body: `<div class="bf">
        <div class="bf__head l">유효구인</div>
        <div class="bf__head">센터</div>
        <div class="bf__head r">유효구직</div>
        ${rows}
      </div>`,
    }));
  }

  // 카드 16 — 〈선택센터〉 상위 산업 · 직종 (감춤: 선택 센터가 없거나, 있어도
  // 그 센터의 행이 하나도 없을 때). 카드 감춤 규칙(화면 규칙 1)의 단일
  // 판단점은 data.hasValue() 하나다(리뷰 지적) — `if (selection.center)`만
  // 보면 "선택이 없다"와 "선택이 없는 데이터를 가리킨다"를 다르게 다뤄
  // 주소를 손으로 고쳐 존재하지 않는 센터를 넣으면 빈 막대 목록만 뜬
  // 카드가 나온다. selection.center 가 undefined 면 hasValue 의 selection
  // 자체가 `{ center: undefined }`라 어차피 못 찾는 값과 같은 길로 감춰진다.
  // selection.occupation/selection.industry 는 절대 안 읽는다(스펙 §4.4
  // 가 명시) — 스위처가 있는 다른 화면과 달리 이 카드는 "그 센터 전체"를
  // 본다.
  //
  // **그 보호막은 바로 아래 한 줄, `selectedRows` 가 아니라 원본
  // `store.vacancy.rows` 를 쓰는 것이다.** 예전 주석은 "이 라우트엔 스위처
  // UI 자체가 없다"고 적어 두었는데 I5 가 그 라우트에 직종 select 를 붙여
  // (app.js 의 SWITCHER_AXIS.center) 더는 사실이 아니다 — 지금은 선택 직종이
  // 실제로 존재하고, 카드 14·15 는 그것으로 걸러진 selectedRows 를 본다.
  // 그러니 "같은 rows 니까" 하며 여기를 selectedRows 로 통일하지 마라. 그
  // 순간 이 카드는 "그 센터 전체의 상위 산업·직종"이 아니라 "선택 직종 하나"가
  // 되고, 상위 직종 절은 막대 한 줄짜리가 된다.
  if (hasValue(store.vacancy.rows, { center: selection.center })) {
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
