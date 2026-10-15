import { api } from "./api.js";
import { BRAND, brandText, pageTitle } from "./brand.js";
import { errorState } from "./components.js";
import { installPointerFx, startBackground } from "./fx.js";
import { playIntro, shouldPlayIntro } from "./intro.js";
import { $, h, icon, installRipples, logo, observeReveal } from "./util.js";
import { CallView } from "./views/call.js";
import { DrillNewView, DrillReportView, DrillsView } from "./views/drills.js";
import { HistoryView } from "./views/history.js";
import { HomeView } from "./views/home.js";
import { JoinView } from "./views/join.js";
import { ReplayView } from "./views/replay.js";
import { ReviewView } from "./views/review.js";
import { StrainsView } from "./views/strains.js";

const NAV = [
  { href: "#/", label: "Home", icon: "home", match: /^#\/$/, tab: true },
  { href: "#/call", label: "Live call", icon: "phone", match: /^#\/(call|chat)$/, tab: true },
  { href: "#/chat", label: "Text chat", icon: "chat", match: /^#\/chat$/, desktopOnly: true, exact: true },
  { href: "#/replay", label: "Replay", icon: "play", match: /^#\/replay(\/(en|hi))?$/, tab: true },
  { href: "#/history", label: "Calls", icon: "list", match: /^#\/(history|call\/.+)$/, tab: true },
  { href: "#/strains", label: "Strains", icon: "virus", match: /^#\/strains$/, tab: true },
  { href: "#/drills", label: "Drills", icon: "users", match: /^#\/drills?(\/.*)?$/, tab: true },
];

const ROUTES = [
  { re: /^#\/$/, title: "", view: () => HomeView() },
  { re: /^#\/call$/, title: "Live call", view: () => CallView({ mode: "voice" }) },
  { re: /^#\/chat$/, title: "Text chat", view: () => CallView({ mode: "text" }) },
  { re: /^#\/replay(?:\/(en|hi))?$/, title: "Replay", view: (m) => ReplayView({ lang: m[1] }) },
  { re: /^#\/history$/, title: "Your calls", view: () => HistoryView() },
  { re: /^#\/call\/([\w-]+)$/, title: "Call review", view: (m) => ReviewView({ id: m[1] }) },
  { re: /^#\/strains$/, title: "Strain library", view: () => StrainsView() },
  { re: /^#\/drills$/, title: "Family drills", view: () => DrillsView() },
  { re: /^#\/drill\/new\/?([\w-]*)$/, title: "Create a family drill", view: (m) => DrillNewView({ strainId: m[1] }) },
  { re: /^#\/drill\/([\w-]+)$/, title: "Drill report", view: (m) => DrillReportView({ id: m[1] }) },
  { re: /^#\/join\/([\w-]+)\/([\w-]+)$/, title: "Practice call", bare: true, view: (m) => JoinView({ id: m[1], key: m[2] }) },
];

const main = $("#view");
let current = null;

function buildShell() {
  const statusDot = h("span", { class: "dot" });
  const statusText = h("span", {}, "Checking…");
  const status = h("span", { class: "status-pill", id: "status", "data-state": "checking", title: "Backend status" }, statusDot, statusText);
  const header = $("#topbar");
  header.replaceChildren(
    h("a", { class: "brand", href: "#/", "aria-label": `${BRAND.name} home` }, logo(), brandText()),
    h("nav", { class: "nav", "aria-label": "Main" }, NAV.map((item) => h("a", { href: item.href, "data-href": item.href, class: item.exact ? "exact" : "" }, item.label))),
    h("span", { class: "grow" }),
    status,
  );
  const tabbar = $("#tabbar");
  tabbar.replaceChildren(
    ...NAV.filter((item) => item.tab).map((item) => h("a", { href: item.href, "data-href": item.href }, icon(item.icon), h("span", {}, item.label))),
  );
  checkBackend(status, statusText);
}

async function checkBackend(status, text, attempt = 0) {
  try {
    const health = await api.health();
    status.dataset.state = health.killSwitch ? "paused" : "online";
    text.textContent = health.killSwitch ? "Live paused" : "Live";
  } catch {
    status.dataset.state = "waking";
    text.textContent = attempt < 4 ? "Waking up…" : "Offline";
    if (attempt < 4) setTimeout(() => checkBackend(status, text, attempt + 1), 3000);
  }
}

function setActive(hash) {
  document.querySelectorAll("[data-href]").forEach((a) => {
    const item = NAV.find((n) => n.href === a.dataset.href);
    const active = item.match.test(hash) && !(hash === "#/chat" && item.href === "#/call");
    a.classList.toggle("active", active);
    if (active) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}

function route() {
  const hash = location.hash || "#/";
  const normalized = hash.replace(/\/+$/, "") || "#/";
  const target = normalized === "#" ? "#/" : normalized;
  let match = null;
  let found = null;
  for (const r of ROUTES) {
    match = target.match(r.re);
    if (match) {
      found = r;
      break;
    }
  }
  current?.destroy?.();
  current = null;
  document.body.classList.toggle("bare", !!found?.bare);
  setActive(target);
  let view;
  try {
    view = found ? found.view(match) : { el: errorState("That page does not exist.", () => (location.hash = "#/")) };
  } catch (err) {
    console.error(err);
    view = { el: errorState("This page failed to load. Please refresh and try again.") };
  }
  current = view;
  document.title = pageTitle(found ? found.title : "Not found");
  main.replaceChildren(view.el);
  main.classList.remove("view-enter");
  void main.offsetWidth;
  main.classList.add("view-enter");
  window.scrollTo({ top: 0 });
  main.focus({ preventScroll: true });
  observeReveal(main);
}

installRipples();
buildShell();
let revealQueued = false;
new MutationObserver(() => {
  if (revealQueued) return;
  revealQueued = true;
  requestAnimationFrame(() => {
    revealQueued = false;
    observeReveal(main);
  });
}).observe(main, { childList: true, subtree: true });
window.addEventListener("hashchange", route);
$("#footer-brand").textContent = BRAND.name;
$("#replay-intro").addEventListener("click", () => {
  location.hash = "#/";
  playIntro();
});
document.title = pageTitle();
startBackground($("#fx"));
installPointerFx();
if (shouldPlayIntro()) playIntro({ onReveal: route });
else route();
