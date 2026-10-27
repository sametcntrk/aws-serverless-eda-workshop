/* Learning layer UI: Tutorial (steps per page, spotlight, mini bar) and the Guided journey (stops across pages). */
import { $, $$, esc } from "./core.js";

let TUT = {}, JOURNEY = [];
let page = "home", steps = [], stepNo = 0;
const tutorOn = () => localStorage.getItem("vt_tutor_off") !== "1";
const doneKey = () => `vt_tutor_done_${page}`;
const smooth = () => (matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth");

export async function initLearnUi() {
  [TUT, JOURNEY] = await Promise.all([fetch("/data/tutorials.json").then((r) => r.json()), fetch("/data/journey.json").then((r) => r.json())]);
  $$("[data-tutor=next]").forEach((b) => b.addEventListener("click", () => {
    if (stepNo >= steps.length - 1) return closeForPage();
    stepNo += 1; render(true);
  }));
  $$("[data-tutor=back]").forEach((b) => b.addEventListener("click", () => { stepNo = Math.max(0, stepNo - 1); render(true); }));
  $$("[data-tutor=close]").forEach((b) => b.addEventListener("click", closeForPage));
  $("#tutor-toggle").addEventListener("click", () => {
    if (!$("#tutor").hidden) localStorage.setItem("vt_tutor_off", "1");
    else { localStorage.setItem("vt_tutor_off", "0"); localStorage.removeItem(doneKey()); stepNo = 0; }
    render();
    if (!$("#tutor").hidden) window.scrollTo({ top: 0, behavior: smooth() });
  });
  $("#journey-start").addEventListener("click", startJourney);
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", onScroll);
}

/** Called by the router on each page change. */
export function setPage(id) {
  page = id;
  steps = (TUT[id] || {}).steps || [];
  stepNo = Number(localStorage.getItem(`vt_tutor_${id}`) || 0);
  render();
  renderJourney();
}

function render(move = false) {
  $$(".spotlight").forEach((el) => el.classList.remove("spotlight"));
  const tutor = $("#tutor");
  if (!steps.length || !tutorOn() || localStorage.getItem(doneKey()) === "1") {
    tutor.hidden = true; $("#tutor-mini").hidden = true; syncToggle(); return;
  }
  stepNo = Math.max(0, Math.min(stepNo, steps.length - 1));
  const s = steps[stepNo], last = stepNo === steps.length - 1;
  tutor.hidden = false;
  $("#tutor-step").textContent = `Tutorial · step ${stepNo + 1} of ${steps.length}`;
  $("#tutor-dots").innerHTML = steps.map((_, i) => `<i class="${i < stepNo ? "done" : i === stepNo ? "now" : ""}"></i>`).join("");
  $("#tutor-title").textContent = s.title;
  $("#tutor-text").textContent = s.text;
  $("#tutor-mini-text").textContent = `Step ${stepNo + 1} of ${steps.length}: ${s.title}`;
  $$("[data-tutor=back]").forEach((b) => { b.disabled = stepNo === 0; });
  $$("[data-tutor=next]").forEach((b) => { b.textContent = last ? "Finish" : "Next"; });
  tutor.classList.remove("tick"); void tutor.offsetWidth; tutor.classList.add("tick");
  const targets = s.target ? $$(s.target) : [];
  targets.forEach((el) => el.classList.add("spotlight"));
  if (move && targets[0]) targets[0].scrollIntoView({ behavior: smooth(), block: "center" });
  localStorage.setItem(`vt_tutor_${page}`, String(stepNo));
  syncToggle();
  checkNav();
}
function closeForPage() { localStorage.setItem(doneKey(), "1"); localStorage.removeItem(`vt_tutor_${page}`); render(); }
function syncToggle() { $("#tutor-toggle").setAttribute("aria-pressed", $("#tutor").hidden ? "false" : "true"); }

// The mini bar appears when the Tutorial buttons are not fully visible, or when the sticky header covers them.
function checkNav() {
  const tutor = $("#tutor");
  if (tutor.hidden) { $("#tutor-mini").hidden = true; return; }
  const n = $("#tutor .tutor-nav").getBoundingClientRect(), h = $(".topbar").getBoundingClientRect();
  const stuck = h.top <= 0.5;
  const visible = n.bottom > 0 && n.top >= 0 && n.bottom <= innerHeight && !(stuck && n.top < h.bottom);
  $("#tutor-mini").hidden = visible;
}
let tick = 0;
function onScroll() { if (!tick) tick = requestAnimationFrame(() => { tick = 0; checkNav(); }); }

/* ---------------- Guided journey */
function renderJourney() {
  const bar = $("#journey"), start = $("#journey-start");
  const at = Number(localStorage.getItem("vt_journey") ?? -1);
  if (at < 0 || !JOURNEY.length) { bar.hidden = true; start.hidden = false; return; }
  start.hidden = true;
  const here = JOURNEY.findIndex((s) => s.page === page);
  const now = here >= 0 ? here : at;
  if (here > at) localStorage.setItem("vt_journey", String(here));
  const next = JOURNEY[now + 1];
  bar.hidden = false;
  bar.innerHTML = `<strong>Guided journey</strong>
    <ol aria-label="Journey progress: stop ${now + 1} of ${JOURNEY.length}">${JOURNEY.map((s, i) => `<li class="${i < now ? "done" : i === now ? "now" : ""}" title="${esc(s.title)}"></li>`).join("")}</ol>
    <span>${now + 1}/${JOURNEY.length} · ${esc(JOURNEY[now].title)}: ${esc(JOURNEY[now].text)}</span>
    ${next ? `<a href="${next.href}" data-link>Next stop: ${esc(next.title)} →</a>` : "<span>You finished the journey.</span>"}
    <button class="lab-btn" type="button" id="journey-stop">Stop</button>`;
  $("#journey-stop").addEventListener("click", () => { localStorage.setItem("vt_journey", "-1"); renderJourney(); });
}
export function startJourney() {
  localStorage.setItem("vt_journey", "0");
  localStorage.setItem("vt_tutor_off", "0");
  Object.keys(localStorage).filter((k) => k.startsWith("vt_tutor_done_")).forEach((k) => localStorage.removeItem(k));
  window.dispatchEvent(new CustomEvent("vt:navigate", { detail: JOURNEY[0].href }));
}
