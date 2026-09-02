const MAX_TITLE = 12;

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
