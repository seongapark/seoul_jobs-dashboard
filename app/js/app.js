import { load } from "./data.js";

const ROUTES = ["overview", "occupation", "industry", "center"];

function currentRoute() {
  const hash = location.hash.replace(/^#\//, "");
  return ROUTES.includes(hash) ? hash : "overview";
}

async function main() {
  const store = await load();
  document.getElementById("headerDate").textContent =
    store.vacancy.period.replace(/(\d{4})(\d{2})/, "$1.$2");

  const render = async () => {
    const route = currentRoute();
    document.querySelectorAll(".segment").forEach((el) =>
      el.classList.toggle("segment--active", el.dataset.route === route));
    const module = await import(`./screens/${route}.js`);
    document.getElementById("screen").innerHTML = module.render(store);
  };

  window.addEventListener("hashchange", render);
  await render();
}

main().catch((err) => {
  document.getElementById("screen").textContent = `데이터를 불러오지 못했습니다: ${err.message}`;
});
