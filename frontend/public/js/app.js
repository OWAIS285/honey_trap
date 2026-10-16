import { api } from "./api.js";
import { BRAND, brandText, pageTitle } from "./brand.js";
import { errorState } from "./components.js";
import { installPointerFx, startBackground } from "./fx.js";
import { playIntro, shouldPlayIntro } from "./intro.js";
import { createCurtain, installCursor, installMagnetic, installScrollProgress } from "./motion.js";
import { $, h, icon, installRipples, logo, observeReveal } from "./util.js";
import { BankInboxView, BanksView } from "./views/banks.js";
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
  { href: "#/call", label: "Live", icon: "phone", match: /^#\/(call|chat)$/, tab: true },
  { href: "#/replay", label: "Replay", icon: "play", match: /^#\/replay(\/(en|hi))?$/, tab: true },
  { href: "#/history", label: "History", icon: "list", match: /^#\/(history|call\/.+)$/, tab: true },
  { href: "#/strains", label: "Strains", icon: "virus", match: /^#\/strains$/, tab: true },
  { href: "#/drills", label: "Drills", icon: "users", match: /^#\/drills?(\/.*)?$/, tab: true },
  { href: "#/banks", label: "Banks", icon: "bank", match: /^#\/banks(\/.*)?$/, tab: true },
];

const ROUTES = [
  { re: /^#\/$/, title: "", view: () => HomeView() },
  { re: /^#\/call$/, title: "Live call", view: () => CallView({ mode: "voice" }) },
  { re: /^#\/chat$/, title: "Text chat", view: () => CallView({ mode: "text" }) },
  { re: /^#\/replay(?:\/(en|hi))?$/, title: "Replay", view: (m) => ReplayView({ lang: m[1] }) },
  { re: /^#\/history$/, title: "History", view: () => HistoryView() },
  { re: /^#\/call\/([\w-]+)$/, title: "Call review", view: (m) => ReviewView({ id: m[1] }) },
  { re: /^#\/strains$/, title: "Strain library", view: () => StrainsView() },
  { re: /^#\/drills$/, title: "Family drills", view: () => DrillsView() },
  { re: /^#\/banks$/, title: "Bank inboxes", view: () => BanksView() },
  { re: /^#\/banks\/([A-Z]{4,10})$/, title: "Bank inbox", view: (m) => BankInboxView({ code: m[1] }) },
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
    h("nav", { class: "nav", "aria-label": "Main" }, NAV.map((item) => h("a", { href: item.href, "data-href": item.href }, item.label))),
    h("div", { class: "top-right" }, status, h("a", { class: "btn primary mini mag nav-cta", href: "#/call" }, icon("phone"), "Take a call")),
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
    const active = item.match.test(hash);
    a.classList.toggle("active", active);
    if (active) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}

function resolve() {
  const hash = location.hash || "#/";
  const normalized = hash.replace(/\/+$/, "") || "#/";
  const target = normalized === "#" ? "#/" : normalized;
  for (const r of ROUTES) {
    const match = target.match(r.re);
    if (match) return { found: r, match, target };
  }
  return { found: null, match: null, target };
}

function route() {
  const { found, match, target } = resolve();
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
  [...view.el.children].forEach((child, i) => child.style.setProperty("--k", String(Math.min(i, 7))));
  main.classList.remove("view-enter");
  void main.offsetWidth;
  main.classList.add("view-enter");
  window.scrollTo({ top: 0, behavior: "instant" });
  main.focus({ preventScroll: true });
  observeReveal(main);
}

installRipples();
buildShell();
const curtain = createCurtain();
let navToken = 0;

// Later page changes: the old page recedes, five panels sweep up with the page name, the new page rises in behind them.
// The first render and reduced motion skip it.
async function navigate() {
  if (location.hash === "#view") return; // the skip link
  const token = ++navToken;
  main.classList.remove("view-enter");
  document.body.classList.add("leaving");
  await curtain.cover(resolve().found?.title || BRAND.name);
  if (token !== navToken) return;
  route();
  document.body.classList.remove("leaving");
  await curtain.uncover();
}
let revealQueued = false;
new MutationObserver(() => {
  if (revealQueued) return;
  revealQueued = true;
  requestAnimationFrame(() => {
    revealQueued = false;
    observeReveal(main);
  });
}).observe(main, { childList: true, subtree: true });
window.addEventListener("hashchange", navigate);
$("#footer-brand").textContent = BRAND.name;
$("#replay-intro").addEventListener("click", () => {
  location.hash = "#/";
  playIntro();
});
document.title = pageTitle();
startBackground($("#fx"));
installPointerFx();
installCursor();
installMagnetic();
installScrollProgress();
if (shouldPlayIntro()) playIntro({ onReveal: route });
else route();
