import { load, parseSelection, selectionHash, optionsFor, reconcileForSido, switcherRows } from "./data.js";
import { esc, AXISLINE_HTML } from "./components.js";

// 지역 선택지는 서울·경기·인천 셋으로 고정한다(R30) — 그 밖의 시도는 이
// 대시보드 범위 밖이라 파일에도 없다.
const SIDO_OPTIONS = [
  { value: "11", label: "서울" },
  { value: "41", label: "경기" },
  { value: "28", label: "인천" },
];

function selectHtml({ id, label, options, value }) {
  const optionTags = options.map((opt) =>
    `<option value="${esc(opt.value)}"${opt.value === value ? " selected" : ""}>${esc(opt.label)}</option>`
  ).join("");
  return `<select class="sel" id="${id}" aria-label="${esc(label)}">${optionTags}</select>`;
}

// 라우트마다 지역 옆에 붙는 축 스위처. 총괄·센터별은 지역뿐이라 여기 없다.
// 한 표에 모아 두면 "그 축을 어느 파일에서 뽑는가"(data.switcherRows)와
// "select 를 어느 id 로 내는가"가 한 자리에서 짝을 이룬다 — C1 은 정확히 그
// 짝이 두 곳으로 흩어져 어긋난 결함이었다.
const SWITCHER_AXIS = {
  occupation: { field: "occupation", id: "selOccupation", label: "직종 선택" },
  industry: { field: "industry", id: "selIndustry", label: "산업 선택" },
};

// 라우트별 스위처(R30, 브리프 표): 총괄=지역, 직종별=지역·직종,
// 산업별=지역·산업, 센터별=지역(축 선택은 Task 14 몫). 네이티브 <select> 를
// 써서 모바일 OS 피커·키보드·스크린리더를 공짜로 얻는다.
function renderSwitcher(route, store, selection) {
  const selects = [selectHtml({
    id: "selSido", label: "지역 선택", options: SIDO_OPTIONS, value: selection.sido,
  })];

  // R41(리뷰 지적) — 지역으로 걸러야 한다. optionsFor 가 sigungu 앞 두
  // 자리(행정표준코드 시도)로 거른다 — 안 거르면 데이터가 없는 (시도,직종)
  // 조합을 고를 수 있어 카드 감춤 규칙이 전부 걸려 화면이 통째로 빈다.
  //
  // C1 — 선택지는 **그 축을 실제로 담은 파일**에서 뽑는다(data.switcherRows).
  // 산업 선택지를 직종 축 파일에서 뽑으면 목록이 영구히 빈다.
  // 선택지가 하나도 없으면(산업 축 파일이 아직 없거나 이 시도에 행이 없다)
  // select 자체를 내지 않는다 — 옵션 없는 select 는 고장으로 읽힌다.
  const axis = SWITCHER_AXIS[route];
  if (axis) {
    const options = optionsFor(switcherRows(store, axis.field) ?? [], axis.field, selection.sido)
      .map((v) => ({ value: v, label: v }));
    if (options.length) {
      selects.push(selectHtml({ id: axis.id, label: axis.label, options, value: selection[axis.field] }));
    }
  }

  return `<div class="switcher">${selects.join("")}</div>`;
}

// 선택을 바꾸는 길은 이것 하나뿐이다(자기 리뷰 항목) — select 가 바뀌면
// location.hash 만 쓰고, 렌더는 기존 hashchange 경로에 맡긴다. 여기서
// 직접 render() 를 부르면 경로가 둘로 갈려 뒤따르는 화면들이 그 위에서
// 흔들린다.
function wireSwitcher(selection, store) {
  const sidoEl = document.getElementById("selSido");
  sidoEl?.addEventListener("change", () => {
    // R41 — 시도가 바뀌면 직종/산업 선택지가 통째로 달라진다.
    // reconcileForSido(순수 함수, data.js)가 지금 선택이 새 목록에도
    // 있으면 유지하고, 없으면 새 목록의 첫 값으로 떨어뜨린다.
    // C1 — 축마다 자기 파일에서 목록을 다시 만든다(renderSwitcher 와 같은
    // switcherRows). 여기서만 store.vacancy 를 쓰면 시도를 바꾼 순간 산업
    // 선택이 "새 목록에 없다"고 판정돼 undefined 로 떨어진다.
    const nextSido = sidoEl.value;
    location.hash = selectionHash({
      ...selection,
      sido: nextSido,
      occupation: reconcileForSido(switcherRows(store, "occupation") ?? [], selection, "occupation", nextSido),
      industry: reconcileForSido(switcherRows(store, "industry") ?? [], selection, "industry", nextSido),
    });
  });

  const bind = (id, field) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", () => {
      location.hash = selectionHash({ ...selection, [field]: el.value });
    });
  };
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
    // 스펙 §4.1 — 스위처 바로 아래 "근무지역 기준" 한 줄(components.AXISLINE_HTML).
    // 라우트 넷이 전부 같은 줄을 쓰므로 화면마다 복사하지 않고 여기 한
    // 곳에서만 붙인다.
    document.getElementById("screen").innerHTML =
      renderSwitcher(selection.route, store, selection) + AXISLINE_HTML + module.render(store, selection);
    wireSwitcher(selection, store);
  };

  window.addEventListener("hashchange", render);
  await render();
}

main().catch((err) => {
  document.getElementById("screen").textContent = `데이터를 불러오지 못했습니다: ${err.message}`;
});
