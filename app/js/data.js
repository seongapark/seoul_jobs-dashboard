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
};

export async function load(base = "../data") {
  const entries = await Promise.all(Object.entries(FILE_OF).map(async ([key, file]) => {
    const res = await fetch(`${base}/${file}.json`);
    if (!res.ok) throw new Error(`${file}.json 을 못 읽었다 (${res.status})`);
    return [key, await res.json()];
  }));
  return Object.fromEntries(entries);
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
