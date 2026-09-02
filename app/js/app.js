import { load, parseSelection, selectionHash } from "./data.js";
import { esc } from "./components.js";

// 지역 선택지는 서울·경기·인천 셋으로 고정한다(R30) — 그 밖의 시도는 이
// 대시보드 범위 밖이라 파일에도 없다.
const SIDO_OPTIONS = [
  { value: "11", label: "서울" },
  { value: "41", label: "경기" },
  { value: "28", label: "인천" },
];

// occupation/industry 선택지는 store.vacancy.rows(시군구 원자료, R20)의
// 고유값을 가나다순으로 뽑는다. 빈 문자열은 뺀다 — est 의 "전직종 합계" 행이
// occupation:"" 을 쓰므로, 안 빼면 그 빈 값이 선택지에 섞여 들어간다.
function uniqueSorted(rows, field) {
  const values = new Set();
  for (const row of rows) {
    if (row[field]) values.add(row[field]);
  }
  return [...values].sort((a, b) => a.localeCompare(b, "ko"));
}

function selectHtml({ id, label, options, value }) {
  const optionTags = options.map((opt) =>
    `<option value="${esc(opt.value)}"${opt.value === value ? " selected" : ""}>${esc(opt.label)}</option>`
  ).join("");
  return `<select class="sel" id="${id}" aria-label="${esc(label)}">${optionTags}</select>`;
}

// 라우트별 스위처(R30, 브리프 표): 총괄=지역, 직종별=지역·직종,
// 산업별=지역·산업, 센터별=지역(축 선택은 Task 14 몫). 네이티브 <select> 를
// 써서 모바일 OS 피커·키보드·스크린리더를 공짜로 얻는다.
function renderSwitcher(route, store, selection) {
  const selects = [selectHtml({
    id: "selSido", label: "지역 선택", options: SIDO_OPTIONS, value: selection.sido,
  })];

  if (route === "occupation") {
    const options = uniqueSorted(store.vacancy.rows, "occupation").map((v) => ({ value: v, label: v }));
    selects.push(selectHtml({ id: "selOccupation", label: "직종 선택", options, value: selection.occupation }));
  }
  if (route === "industry") {
    const options = uniqueSorted(store.vacancy.rows, "industry").map((v) => ({ value: v, label: v }));
    selects.push(selectHtml({ id: "selIndustry", label: "산업 선택", options, value: selection.industry }));
  }

  return `<div class="switcher">${selects.join("")}</div>`;
}

// 선택을 바꾸는 길은 이것 하나뿐이다(자기 리뷰 항목) — select 가 바뀌면
// location.hash 만 쓰고, 렌더는 기존 hashchange 경로에 맡긴다. 여기서
// 직접 render() 를 부르면 경로가 둘로 갈려 뒤따르는 화면들이 그 위에서
// 흔들린다.
function wireSwitcher(selection) {
  const bind = (id, field) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", () => {
      location.hash = selectionHash({ ...selection, [field]: el.value });
    });
  };
  bind("selSido", "sido");
  bind("selOccupation", "occupation");
  bind("selIndustry", "industry");
}

// Step 6b — 화면 모듈은 문자열 HTML 만 돌려주므로 스스로 이벤트를 못
// 붙인다. #screen 에 위임 클릭/키보드 핸들러를 하나만 둔다: [data-nav] 가
// 이미 selectionHash 로 만들어 둔 해시 문자열을 location.hash 에 옮기는
// 것 말고는 아무 것도 하지 않는다 — 이 경로도 결국 hashchange 로 합류한다.
function wireNavDelegation() {
  const screen = document.getElementById("screen");
  const navigate = (target) => {
    const el = target.closest("[data-nav]");
    if (el) location.hash = el.dataset.nav;
  };
  screen.addEventListener("click", (e) => navigate(e.target));
  screen.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const el = e.target.closest("[data-nav]");
    if (!el) return;
    e.preventDefault(); // Space 의 기본 동작(스크롤)을 막는다
    navigate(e.target);
  });
}

async function main() {
  const store = await load();
  document.getElementById("headerDate").textContent =
    store.vacancy.period.replace(/(\d{4})(\d{2})/, "$1.$2");

  wireNavDelegation();

  const render = async () => {
    const selection = parseSelection(location.hash);
    document.querySelectorAll(".segment").forEach((el) =>
      el.classList.toggle("segment--active", el.dataset.route === selection.route));
    const module = await import(`./screens/${selection.route}.js`);
    document.getElementById("screen").innerHTML =
      renderSwitcher(selection.route, store, selection) + module.render(store, selection);
    wireSwitcher(selection);
  };

  window.addEventListener("hashchange", render);
  await render();
}

main().catch((err) => {
  document.getElementById("screen").textContent = `데이터를 불러오지 못했습니다: ${err.message}`;
});
