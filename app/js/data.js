const MAX_TITLE = 12;

// 마감년월 "202607" -> "2026.07" 표시용. overview 가 먼저 냈고 직종별·
// 산업별 화면이 그대로 가져다 쓴다 — 화면마다 복사하지 않는다.
export const period = (p) => p.replace(/(\d{4})(\d{2})/, "$1.$2");

// est 의 반기 코드(예 "202601")를 "'26 상반기" 로. 01월 수집은 상반기,
// 07월 수집은 하반기를 뜻한다(집계 관행).
export const half = (p) => `’${p.slice(2, 4)} ${p.slice(4) === "01" ? "상반기" : "하반기"}`;

// 전년동월대비(R32)가 찾는 "같은 달, 1년 전" 마감년월. overview 카드4와
// 직종별 카드8이 똑같이 쓴다 — 시계열에 찾는 축(occupation 등)이 없으면
// find 가 그냥 못 찾을 뿐이고, 이 함수 자체는 축을 모른다.
export function priorYearPeriod(p) {
  return String(Number(p.slice(0, 4)) - 1) + p.slice(4);
}

// 제목 12자 규칙 — 화면 규칙 2. 12자를 넘으면 잘라내고 말줄임표를 붙인다.
export function titleFor(name, suffix) {
  const head = name.length > MAX_TITLE ? name.slice(0, MAX_TITLE) + "…" : name;
  return suffix ? `${head} ${suffix}` : head;
}

// 구인배수 = 유효구인 / 유효구직, 소수 둘째 자리. 분모가 0(또는 없음)이면 null —
// 화면은 null 을 "—" 로 그린다.
export function ratio(vacancy, seekers) {
  if (!seekers) return null;
  return Math.round((vacancy / seekers) * 100) / 100;
}

// R20 — 시군구 파일과 시도 파일을 서로 헷갈릴 수 없는 다른 키로 각각 싣는다.
// vacancy_sido.json 을 vacancy 키에 실으면(이전 버전의 실수) 직종별·센터별
// 화면이 시군구가 필요할 때 조용히 시도 행을 받는다 — 에러도 크래시도 없이
// 축만 틀리게 그려지는, 이 프로젝트에서 가장 나쁜 실패 모양이다. 그래서
// vacancy/placement/insured 는 시군구 원자료 그대로, vacancySido/
// placementSido/insuredSido 는 R4(시도 값은 시군구 합으로 만들지 않는다)에
// 따라 별도 수집된 시도 파일이다. mobility·est·centerMap 은 파일이 하나뿐이라
// 그대로 싣는다.
const FILE_OF = {
  vacancy: "vacancy",
  placement: "placement",
  insured: "insured",
  vacancySido: "vacancy_sido",
  placementSido: "placement_sido",
  insuredSido: "insured_sido",
  mobility: "mobility",
  est: "est",
  centerMap: "center_map",
  // 자치구별·센터별 막대의 라벨용 시군구 코드→이름 표. 이미 저장소에
  // 커밋돼 있어(파이프라인 산출물이 아니다) 아홉 개와 같이 필수로 싣는다.
  sigunguNames: "sigungu_names",
  // 센터별 화면(Task 14)의 타일 카토그램 배치 — 승인된 목업에서 그대로 뽑은
  // 70칸 좌표표라 위 둘과 마찬가지로 저장소에 커밋돼 있다(파이프라인 산출물이
  // 아니다). 파이프라인 배선을 기다릴 이유가 없어 필수로 싣는다.
  tileLayout: "tile_layout",
};

// R31 — 마감년월 축 시계열은 수집이 아직 이력을 다 쌓지 못했을 수 있다.
// 위 FILE_OF(아홉 개 + 시군구 이름표)는 지금처럼 404 면 예외를 내는 필수
// 파일이지만, 이 넷은 없어도 화면이 서야 한다: 404 면 키 자체를 비워
// 두고(undefined) 나머지를 싣는다. 그 위에 선 카드(추세·전년동월대비)는
// hasValue 가 알아서 감춘다 — 데이터 태스크와 화면 태스크가 서로를 막지
// 않는다(R32도 같은 원칙). 산업 축은 직종 축과 다른 그리드로 받아야 해서
// 파일이 따로 생긴다.
const OPTIONAL_FILE_OF = {
  vacancySeries: "vacancy_series",
  insuredSeries: "insured_series",
  vacancyIndustry: "vacancy_industry",
  insuredIndustry: "insured_industry",
  // C2 — 산업별 KOSIS 표(DT_118N_DEN061)는 직종별 표와 다른 파일이다. 반기
  // 수집이 한 번이라도 돌기 전에는 없으므로 선택 파일이다(est.json 은 필수).
  estIndustry: "est_industry",
};

export async function load(base = "../data") {
  const required = await Promise.all(Object.entries(FILE_OF).map(async ([key, file]) => {
    const res = await fetch(`${base}/${file}.json`);
    if (!res.ok) throw new Error(`${file}.json 을 못 읽었다 (${res.status})`);
    return [key, await res.json()];
  }));
  const optional = await Promise.all(Object.entries(OPTIONAL_FILE_OF).map(async ([key, file]) => {
    const res = await fetch(`${base}/${file}.json`);
    if (!res.ok) return [key, undefined];
    return [key, await res.json()];
  }));
  return Object.fromEntries([...required, ...optional]);
}

// I4 — 스펙 §5.2 "마지막 성공 시점". 왜 45일인가:
//
// 수집 실패는 조용하다. 검사가 하나라도 어긋나면 워크플로가 죽어 커밋 단계에
// 닿지 못하고, data/*.json 은 지난달 것이 그대로 남는다(그게 옳은 설계다 —
// 절반만 갱신된 상태가 가장 나쁘다). 그런데 화면 헤더는 그 파일의 **자료
// 기준월**만 보여주므로, 수집이 석 달 실패해도 화면은 아무 말 없이 옛
// 기준월을 최신인 양 띄운다. 스펙이 그 이유까지 적었다 — "센터가 오래된 값을
// 최신인 줄 알고 인용하는 일이 없어야 한다."
//
// 임계는 수집 주기에서 나온다. `.github/workflows/collect-monthly.yml` 이
// 매월 5일에 도니까 연속 두 번의 성공은 28~31일 간격이다. 그래서
//   - 31일보다 넉넉히 크게(정상 주기와 cron 지연을 오탐하지 않게)
//   - 62일(=한 번 걸렀을 때 다음 성공까지)보다는 작게
// 잡아야 "한 번의 실패"가 실제로 드러난다. 45일이 그 사이에서 양쪽에 여유가
// 가장 고른 값이다. 더 짧게 잡으면 늦게 도는 잡마다 배너가 떠 사람이 배너를
// 무시하게 되고, 더 길게 잡으면 한 달치 결측이 조용히 지나간다.
export const STALE_AFTER_DAYS = 45;

const MS_PER_DAY = 24 * 60 * 60 * 1000;

// 배너에 쓸 문구를 낸다 — 신선하면 null(배너 없음). 순수 함수라 `now` 를
// 주입받는다(테스트가 시계를 기다리지 않는다).
//
// collected_at 이 없거나 못 읽는 값이면 **조용히 넘어가지 않고** 그 사실을
// 띄운다. 침묵은 "최신"과 구별되지 않는데, 이 화면에서 그 둘을 헷갈리는 것이
// 정확히 스펙이 막으려던 사고다.
export function staleNotice(dataset, now = new Date()) {
  const stamp = dataset?.collected_at;
  if (!stamp) return "마지막 수집 시점을 알 수 없습니다 — 값이 최신인지 확인하세요.";
  const collected = new Date(stamp);
  if (Number.isNaN(collected.getTime())) {
    return "마지막 수집 시점을 읽지 못했습니다 — 값이 최신인지 확인하세요.";
  }
  const days = Math.floor((now.getTime() - collected.getTime()) / MS_PER_DAY);
  if (days <= STALE_AFTER_DAYS) return null;
  // 날짜는 스탬프 문자열에서 그대로 잘라 쓴다(UTC 기준) — 보는 사람의 시간대에
  // 따라 하루씩 달라 보이지 않게 한다.
  const date = String(stamp).slice(0, 10).replace(/-/g, ".");
  return `마지막 수집 성공: ${date} (${days}일째 갱신 없음) — 값이 최신이 아닐 수 있습니다.`;
}

const ROUTES = ["overview", "occupation", "industry", "center"];
const SCOPES = ["수도권", "서울", "경기", "인천"];

// application/x-www-form-urlencoded(URLSearchParams)는 공백을 '+'로 바꾸는
// 등 encodeURIComponent 와 결이 달라 예제 해시(%EA%B2%BD…)와 안 맞는다.
// 그래서 쿼리 문자열을 직접 나눠 decodeURIComponent/encodeURIComponent 로
// 왕복시킨다 — 이 둘이 항상 짝을 이룬다.
function parseQuery(queryPart) {
  const out = {};
  if (!queryPart) return out;
  for (const pair of queryPart.split("&")) {
    if (!pair) continue;
    const eqIndex = pair.indexOf("=");
    const key = eqIndex === -1 ? pair : pair.slice(0, eqIndex);
    const value = eqIndex === -1 ? "" : pair.slice(eqIndex + 1);
    out[decodeURIComponent(key)] = decodeURIComponent(value);
  }
  return out;
}

function buildQuery(paramsObj) {
  return Object.entries(paramsObj)
    .filter(([, v]) => v != null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join("&");
}

// 선택 상태를 주소에서 되읽는다. sido 만 기본값(서울 "11")을 가진다 —
// occupation/industry/center 는 없으면 반드시 undefined 여야 한다. 빈
// 문자열로 만들면 est 행이 "전직종 합계"를 나타낼 때 쓰는 실제 occupation
// 값("")과 조용히 겹쳐 오매칭된다.
export function parseSelection(hash) {
  const raw = String(hash ?? "").replace(/^#\/?/, "");
  const qIndex = raw.indexOf("?");
  const routePart = qIndex === -1 ? raw : raw.slice(0, qIndex);
  const queryPart = qIndex === -1 ? "" : raw.slice(qIndex + 1);
  const route = ROUTES.includes(routePart) ? routePart : "overview";
  const q = parseQuery(queryPart);
  return {
    route,
    sido: q.sido ?? "11",
    occupation: q.occupation,
    industry: q.industry,
    center: q.center,
    scope: SCOPES.includes(q.scope) ? q.scope : "수도권",
    sigungu: q.sigungu,
  };
}

// parseSelection 의 짝. selectionHash(selection) -> "#/occupation?sido=11&…"
// parseSelection(selectionHash(s)) 이 s 를 되돌려야 한다(선택 왕복).
export function selectionHash(selection = {}) {
  const route = ROUTES.includes(selection.route) ? selection.route : "overview";
  const query = buildQuery({
    sido: selection.sido,
    occupation: selection.occupation,
    industry: selection.industry,
    center: selection.center,
    scope: selection.scope,
    sigungu: selection.sigungu,
  });
  const path = route === "overview" ? "" : route;
  return `#/${path}${query ? `?${query}` : ""}`;
}

// 카드 감춤 규칙(화면 규칙 1)의 단일 판단점. rows 안에 selection 의 모든
// key:value 가 일치하는 행이 하나라도 있으면 값이 "있다". 총괄·직종별 등
// 모든 화면이 이 함수 하나로 카드 표시 여부를 정한다 — 화면마다 각자
// find()/조건문을 다시 짜지 않는다.
export function hasValue(rows, selection) {
  if (!rows) return false;
  return rows.some((row) =>
    Object.entries(selection).every(([key, want]) => row[key] === want));
}

// 시군구 원자료(vacancy/placement/insured, 그리고 같은 그리드인 vacancyIndustry/
// insuredIndustry)를 시도로 거른다. 이 행들엔 sido 필드가 없고 sigungu 코드
// (행정표준코드)의 앞 두 자리가 시도다(서울 11·경기 41·인천 28). row.sido로
// 걸러버리면 시군구 행 전부가 필터를 통과 못 해 카드가 조용히 다 사라진다
// (R22) — 그래서 이 함수 하나로 통일해 그 실수를 한 곳에서만 낼 수 있게
// 막는다. mobility 처럼 시도 축 그 자체인 행(row.sido 존재)에는 쓰지 않는다
// — 그건 그냥 row.sido === sido 로 거른다(R35).
export function inSido(rows, sido) {
  return rows.filter((r) => r.sigungu && r.sigungu.startsWith(sido));
}

// 시군구별로 쪼개진 값을 한 필드 기준으로 합산한다. 직종별·산업별 화면이
// 똑같이 "선택 시도 안 시군구 합"을 여러 필드(유효구인·유효구직·피보험자·
// 취득·상실…)에 반복해서 구해 화면마다 다시 짜지 않는다.
export function sumBy(rows, field) {
  return rows.reduce((s, r) => s + (r[field] ?? 0), 0);
}

// sigunguNames 표의 "서울특별시 종로구" 에서 시도 접두(첫 단어)를 뺀 짧은
// 이름("종로구")을 낸다 — 480px 폭에서 자치구별 막대·지도 선택 패널 라벨이
// 전체 이름이면 넘친다. 직종별 화면(Task 12)이 먼저 만들었고 센터별 화면
// (Task 14)도 그대로 쓰므로 여기로 올렸다 — 화면마다 복사하지 않는다. 표에
// 없는 코드는 코드를 그대로 보여준다(폴백을 지어내지 않는다).
export function shortSigunguName(sigunguNames, code) {
  const full = sigunguNames?.[code];
  if (!full) return code;
  const parts = full.split(" ");
  return parts.length > 1 ? parts.slice(1).join(" ") : full;
}

// R41(리뷰 지적) — 스위처 선택지는 지역으로 걸러야 한다. 시군구 축 행에는
// sido 필드가 없다(sigungu/center 뿐) — 시군구 코드가 행정표준코드라 앞
// 두 자리가 시도다(서울 "11"·경기 "41"·인천 "28"). 안 거르면 데이터가
// 하나도 없는 (시도,직종) 조합을 고를 수 있고, 그러면 hasValue 가 카드를
// 전부 감춰 화면이 통째로 빈다 — 사용자 눈엔 "앱이 고장났다"와 구별 안 된다.
// 빈 문자열은 뺀다(est 의 "전직종 합계" 행이 occupation:"" 을 쓴다).
export function optionsFor(rows, field, sido) {
  const values = new Set();
  for (const row of rows) {
    if (row.sigungu && row.sigungu.startsWith(sido) && row[field]) values.add(row[field]);
  }
  return [...values].sort((a, b) => a.localeCompare(b, "ko"));
}

// C1 — **스위처의 축과 그것을 담은 파일은 짝이 맞아야 한다.** 직종 축 그리드
// (vacancy.json)와 산업 축 그리드(vacancy_industry.json)는 EIS 에서 레이아웃을
// 달리해 따로 받는 별개의 파일이고, eis.collect_vacancy 는 그 그리드에 없는
// 축을 빈 문자열로 채운다. 그래서 산업 선택지를 store.vacancy 에서 뽑으면
// optionsFor 의 빈 문자열 필터에 전부 걸려 목록이 **영구히 빈다** — 그러면
// 산업별 탭에서 카드 11·12·13 에 도달할 길이 아예 없고, 카드 감춤 규칙(화면
// 규칙 1)이 그 사실을 완벽히 숨겨 "데이터가 원래 없나 보다"로 읽힌다.
// vacancyIndustry 는 선택 파일이라(R31) 아직 수집이 없으면 undefined 다 —
// 그때는 빈 목록이 아니라 undefined 를 돌려주어, 부르는 쪽이 "선택지가 없는
// select" 를 그리는 대신 select 자체를 안 내도록 한다.
export function switcherRows(store, field) {
  return field === "industry" ? store.vacancyIndustry?.rows : store.vacancy.rows;
}

// I5 — 스위처 선택지를 어느 시도로 거를 것인가. 라우트마다 "지금 보고 있는
// 지역"을 정하는 것이 다르다: 총괄·직종별·산업별은 지역 select(selection.sido)
// 지만, 센터별은 **지도 칩(scope)** 이다(그 화면의 카드 14·15 는 selection.sido
// 를 아예 안 읽는다). 그걸 안 맞추면 scope=경기 로 지도를 보면서 서울에만
// 있는 직종을 고를 수 있고, 그러면 지도가 통째로 회색이 된다 — R41 이 막으려던
// "화면이 비어 고장으로 보이는" 실패 그대로다. scope 가 "수도권"이면 특정 시도가
// 없으므로 ""로 두어 optionsFor 의 startsWith("") 가 전부 통과시키게 한다.
export function switcherSido(selection, sidoOfScope) {
  if (selection.route !== "center") return selection.sido;
  return sidoOfScope[selection.scope] ?? "";
}

// I6 — "지금 선택이 이 목록에서 성립하는가"를 판단하는 한 자리.
//
// 지금 선택이 목록에 있으면 그대로 두고, 없으면(다른 시도에만 있던 값이거나
// **첫 진입이라 아예 없거나**) 목록의 첫 값으로 떨어뜨린다. 목록이 비어 있으면
// undefined — parseSelection 이 기대하는 "없음"과 같은 모양이고, 없는 선택을
// 지어내지 않는다.
//
// 첫 진입을 함께 다루는 것이 이 함수의 핵심이다. parseSelection 은
// occupation/industry 를 의도적으로 undefined 로 두는데(빈 문자열은 est 의
// 실제 값 ""과 오매칭된다) 그 뒤에 아무도 기본값을 채우지 않아, `#/occupation`
// 첫 진입이 이런 먹통이 됐다: 브라우저는 첫 옵션을 표시하는데 selection 은
// undefined 라 카드가 다 감춰지고, 사용자가 **화면에 보이는 그 직종을 다시
// 골라도** change 이벤트가 안 나서 아무 일도 일어나지 않는다. 상담 창구에서
// 가장 먼저 겪을 장면이다.
export function resolveAxis(rows, selection, field, sido) {
  const options = optionsFor(rows ?? [], field, sido);
  return options.includes(selection[field]) ? selection[field] : options[0];
}

// 시도를 바꿀 때 쓰는 짝. resolveAxis 와 판단은 같고, "이 라우트에 그 축이
// 애초에 없으면(선택이 null) 손대지 않는다"는 규칙만 앞에 둔다 — 이 함수는
// 라우트를 모른 채 occupation·industry 둘 다에 대해 불리기 때문이다.
export function reconcileForSido(rows, selection, field, nextSido) {
  if (selection[field] == null) return selection[field];
  return resolveAxis(rows, selection, field, nextSido);
}

// 지역 select 를 바꿨을 때의 다음 선택 전체. app.js 의 이벤트 핸들러가 이
// 한 줄만 부르게 해서, **화해 기준을 정하는 판단이 두 곳으로 갈라질 수 없게**
// 한다(재리뷰 지적).
//
// 갈라지면 이렇게 된다: 선택지를 거르는 기준(renderSwitcher·resolveSelection)은
// switcherSido — 센터별이면 지도 칩(scope) — 인데 화해만 nextSido 를 그대로
// 쓰면, 센터별에서 지역 select 를 바꾼 순간 직종이 그 시도 목록의 첫 값으로
// 밀려나고 렌더 쪽은 그 값이 지금 목록에도 있으니 그냥 받아들인다. **지도
// 범위는 그대로인데 직종만 몰래 바뀌어 카드 14·15 값이 통째로 달라진다** —
// 사용자가 지시하지 않은 변화다. 그래서 기준을 여기 한 번만 계산한다.
//
// 지역 select 자체는 센터별에서도 남는다: 그 화면의 지도 범위는 칩이 정하지만
// **직종 선택지의 기준 지역**은 여전히 이 select 다(switcherSido 가 scope 를
// 쓰는 것은 칩이 특정 시도를 가리킬 때뿐이고, 수도권이면 세 시도를 다 연다).
export function reconcileSelectionForSido(store, selection, nextSido, sidoOfScope) {
  const next = { ...selection, sido: nextSido };
  const sido = switcherSido(next, sidoOfScope);
  return {
    ...next,
    occupation: reconcileForSido(switcherRows(store, "occupation") ?? [], selection, "occupation", sido),
    industry: reconcileForSido(switcherRows(store, "industry") ?? [], selection, "industry", sido),
  };
}
