// app/tests/tilemap.test.js — tilemap.js 의 step()/render() 와
// data/tile_layout.json 자체의 무결성. 목업 70칸 배치를 코드로 옮기는
// 변환이 이 태스크에서 가장 틀리기 쉬운 지점이라(브리프 경고) 파일 자체를
// 이 테스트가 직접 읽어 단언한다 — 변환 스크립트는 버려도 이 보증은 남는다.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { step, render } from "../js/tilemap.js";

const failed0 = 0;
let failed = failed0;
const has = (html, needle, label) => {
  if (!html.includes(needle)) { failed++; console.error(`FAIL ${label}`); }
  else console.log(`ok ${label}`);
};
const hasNot = (html, needle, label) => {
  if (html.includes(needle)) { failed++; console.error(`FAIL ${label}`); }
  else console.log(`ok ${label}`);
};
const eq = (got, want, label) => {
  if (got !== want) { failed++; console.error(`FAIL ${label}: ${got} !== ${want}`); }
  else console.log(`ok ${label}`);
};
const ok = (cond, label) => {
  if (!cond) { failed++; console.error(`FAIL ${label}`); }
  else console.log(`ok ${label}`);
};

const BREAKS = [0.08, 0.12, 0.18, 0.25];

// 1. step 경계 — 4개 breaks 로 1~5단계. 경계값 자체(0.08)가 아래 단계가
// 아니라 위 단계로 붙는지가 가장 틀리기 쉬운 지점이라 따로 핀한다.
eq(step(0.05, BREAKS), 1, "breaks[0] 미만은 1단계");
eq(step(0.08, BREAKS), 2, "경계값 0.08 은 그 자체로 2단계(1단계가 아니다)");
eq(step(0.079999, BREAKS), 1, "0.08 바로 아래는 여전히 1단계");
eq(step(0.12, BREAKS), 3, "경계값 0.12 는 3단계");
eq(step(0.18, BREAKS), 4, "경계값 0.18 은 4단계");
eq(step(0.25, BREAKS), 5, "경계값 0.25 는 5단계");
eq(step(0.30, BREAKS), 5, "breaks[3] 이상은 5단계");

// 이하 render() 검증용 최소 레이아웃 — 서울/경기/인천 시도가 하나씩 있고,
// "41199"는 어느 store 에도 값이 없는 코드로 둬 "값 없음" 타일을 확인한다.
const layout = {
  "11110": { row: 1, col: 1, sido: "11", name: "종로구" },
  "41110": { row: 1, col: 2, sido: "41", name: "수원시" },
  "28110": { row: 1, col: 3, sido: "28", name: "중구" },
  "41199": { row: 2, col: 1, sido: "41", name: "값없는시" },
};

// 2. 값이 없는 코드는 1단계(가장 옅은 램프색)가 아니라 회색 빈 타일로
// 그린다 — "값 없음"을 "가장 낮은 값"으로 보이게 하면 지도가 거짓말한다.
const values = { "11110": 0.05, "41110": 0.30, "28110": 0.10 }; // "41199" 는 없음
const html = render(values, layout, {});
has(html, '(값 없음)', "값 없는 타일의 title/aria-label 이 값 없음을 말한다");
// 값 없는 타일 하나만 뽑아 그 style 에 램프 변수(--g/--s/--i)가 전혀 없는지 확인.
const emptyTileMatch = html.match(/<i[^>]*data-code="41199"[^>]*>/);
ok(!!emptyTileMatch, "41199 타일이 그려진다");
ok(!/var\(--[sgi]\d\)/.test(emptyTileMatch[0]), "값 없는 타일은 램프 색 변수를 쓰지 않는다");

// 3. 시도별 램프 — 서울 --s, 경기 --g, 인천 --i.
has(html, 'data-code="11110"', "서울 타일이 그려진다");
const seoulTile = html.match(/<i[^>]*data-code="11110"[^>]*>/)[0];
ok(/var\(--s[1-5]\)/.test(seoulTile), "서울 타일은 --s 램프를 쓴다");
const gyeonggiTile = html.match(/<i[^>]*data-code="41110"[^>]*>/)[0];
ok(/var\(--g[1-5]\)/.test(gyeonggiTile), "경기 타일은 --g 램프를 쓴다");
const incheonTile = html.match(/<i[^>]*data-code="28110"[^>]*>/)[0];
ok(/var\(--i[1-5]\)/.test(incheonTile), "인천 타일은 --i 램프를 쓴다");

// scope 가 수도권이 아니면 그 시도 타일만 그린다.
const htmlSeoulOnly = render(values, layout, { scope: "서울" });
has(htmlSeoulOnly, 'data-code="11110"', "scope=서울 이면 서울 타일이 나온다");
hasNot(htmlSeoulOnly, 'data-code="41110"', "scope=서울 이면 경기 타일이 안 나온다");
hasNot(htmlSeoulOnly, 'data-code="28110"', "scope=서울 이면 인천 타일이 안 나온다");

// 선택된 타일엔 on 클래스, title/aria-label 에 값이 함께 나온다(화면 규칙 5
// — 색만으로 못 읽는다).
const htmlSel = render(values, layout, { selected: "11110" });
has(htmlSel, 'class="tile on"', "선택된 타일에 on 클래스가 붙는다");
has(htmlSel, "종로구 구인배수 0.05", "title/aria-label 에 이름과 값이 함께 나온다");

// navOf 콜백이 각 타일의 data-nav 를 만든다.
const htmlNav = render(values, layout, { navOf: (code) => `#/center?sigungu=${code}` });
has(htmlNav, 'data-nav="#/center?sigungu=11110"', "navOf 콜백 결과가 data-nav 에 실린다");

// 4. data/tile_layout.json 자체의 무결성 — 목업 70칸 변환이 하나라도
// 어긋나면 여기서 실패한다(조용히 빠지지 않는다, 브리프의 핵심 경고).
const layoutPath = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)), "../../data/tile_layout.json");
const tileLayout = JSON.parse(readFileSync(layoutPath, "utf8"));
const codes = Object.keys(tileLayout);
eq(codes.length, 70, "타일 배치가 70칸 전부 옮겨졌다");
eq(new Set(codes).size, 70, "코드가 하나도 겹치지 않는다");
const badSido = codes.filter((c) => !["11", "41", "28"].includes(tileLayout[c].sido));
eq(badSido.length, 0, "sido 는 11(서울)·41(경기)·28(인천) 뿐이다(31 이 아니다)");
const badRowCol = codes.filter((c) => {
  const t = tileLayout[c];
  return !Number.isInteger(t.row) || !Number.isInteger(t.col) || t.col < 1 || t.col > 15;
});
eq(badRowCol.length, 0, "row/col 이 정수이고 col 은 1..15 안이다");
// 코드 앞 두 자리가 sido 필드와 실제로 일치하는지(자기모순 방지).
const mismatched = codes.filter((c) => c.slice(0, 2) !== tileLayout[c].sido);
eq(mismatched.length, 0, "코드 앞 두 자리와 sido 필드가 일치한다");

process.exit(failed ? 1 : 0);
