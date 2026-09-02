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

// R4 — 시도 단위 값은 시군구 합으로 만들지 않는다(유효구직건수는 1인 다건이라
// 부분의 합이 전체를 넘는다). 총괄·직종별·산업별 화면은 시도 단위로 거르므로
// vacancy/placement/insured 는 시군구 원자료(vacancy.json 등)가 아니라
// pipeline/collect.py 가 별도로 낸 *_sido.json 을 읽는다. mobility·est 는
// 애초에 시도 단위라 그대로 쓴다.
const FILE_OF = {
  vacancy: "vacancy_sido",
  placement: "placement_sido",
  insured: "insured_sido",
  mobility: "mobility",
  est: "est",
  center_map: "center_map",
};

export async function load(base = "../data") {
  const entries = await Promise.all(Object.entries(FILE_OF).map(async ([key, file]) => {
    const res = await fetch(`${base}/${file}.json`);
    if (!res.ok) throw new Error(`${file}.json 을 못 읽었다 (${res.status})`);
    return [key, await res.json()];
  }));
  return Object.fromEntries(entries);
}
