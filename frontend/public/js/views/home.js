import { BRAND } from "../brand.js";
import { initSplit, pinnedStory, velocityMarquee } from "../motion.js";
import { createOrb } from "../orb3d.js";
import { scriptPanel } from "../scripts.js";
import { SCAM_LABELS, countUp, h, icon, observeReveal, reducedMotion } from "../util.js";

const link = (href, cls, ...children) => h("a", { href, class: cls }, ...children);

function marquee() {
  const labels = Object.entries(SCAM_LABELS).filter(([id]) => id !== "not_scam" && id !== "undetermined").map(([, label]) => label);
  const row = () => labels.map((label) => h("span", { class: "mq-item" }, h("i"), label));
  return h(
    "section",
    { class: "marquee reveal" },
    h("p", { class: "eyebrow marquee-label center" }, "Scam strains it recognises"),
    h("div", { class: "marquee-track", "aria-hidden": "true" }, row(), row()),
  );
}

function ticker() {
  const words = ["Stall", "Trap", "Strain", "Vaccinate", "Evidence"];
  const row = () => words.map((word, i) => h("span", { class: `tk ${i % 2 ? "outline" : ""}` }, word));
  const track = h("div", { class: "tk-track" }, row(), row());
  return { el: h("section", { class: "ticker", "aria-hidden": "true" }, track), track };
}

function heroStage() {
  const canvas = h("canvas", { class: "orb-canvas", "aria-hidden": "true" });
  const bubble = (who, text, cls, delay) => h("div", { class: `mock-bubble ${cls}`, style: { "--d": `${delay}s` } }, h("small", {}, who), h("p", { lang: "en" }, text));
  const chip = (ico, label, value, delay, cls) => h("div", { class: `mock-chip ${cls}`, style: { "--d": `${delay}s` } }, icon(ico), h("div", {}, h("small", {}, label), h("b", {}, value)));
  const el = h(
    "div",
    { class: "hero-stage", "aria-hidden": "true" },
    h("div", { class: "orb-fallback" }),
    canvas,
    h("div", { class: "stage-ring r1" }),
    h("div", { class: "stage-ring r2" }),
    chip("clock", "Scammer's time wasted", "02:47 and counting", 1.2, "c3"),
    chip("shield", "Scam type", "Digital arrest · 94%", 3.2, "c2"),
    chip("card", "UPI ID caught", "rahul.sharma@okaxis", 5.8, "c1"),
    h(
      "div",
      { class: "stage-captions" },
      bubble("Caller", "A parcel in your name has illegal items. Pay 50,000 now.", "caller", 0.4),
      bubble("Ramesh", "Which parcel, sir? I never ordered anything... say the UPI ID slowly.", "persona", 2.4),
      bubble("Caller", "rahul dot sharma at okaxis.", "caller", 4.6),
    ),
  );
  const orb = createOrb(canvas);
  el.classList.toggle("gl", !!orb);
  let timer = 0;
  if (orb && !reducedMotion()) {
    // The orb "talks" in bursts, roughly following the captions beside it.
    const t0 = performance.now();
    timer = setInterval(() => {
      const t = (performance.now() - t0) / 1000;
      const speech = Math.max(0, Math.sin(t * 2.3) * Math.sin(t * 0.7 + 1)) * 0.55;
      orb.setEnergy(0.2 + speech);
    }, 60);
  }
  return {
    el,
    destroy() {
      clearInterval(timer);
      orb?.destroy();
    },
  };
}

const bars = () => h("div", { class: "mock-wave" }, Array.from({ length: 26 }, (_, i) => h("i", { style: { "--i": i } })));

function sceneTrap() {
  return h(
    "div",
    { class: "scene" },
    h(
      "div",
      { class: "sc-card card" },
      h("div", { class: "sc-head" }, h("span", { class: "live-dot" }, "LIVE"), h("small", {}, "Ramesh · 02:47")),
      bars(),
      h("div", { class: "sc-line caller" }, h("small", {}, "Caller"), h("p", { lang: "en" }, "Send fifty thousand now. UPI: rahul dot sharma at okaxis.")),
      h("div", { class: "sc-line persona" }, h("small", {}, "Ramesh"), h("p", { lang: "en" }, "Slowly, sir... say that ID once more?")),
      h("div", { class: "sc-chip" }, icon("check"), h("div", {}, h("small", {}, "UPI ID caught"), h("b", { class: "mono" }, "rahul.sharma@okaxis")), h("span", { class: "badge ok" }, "Confirmed")),
    ),
  );
}

function sceneStrain() {
  const steps = ["Claims a parcel in the victim's name holds illegal items.", "Says an arrest warrant is ready.", "Orders: stay on the line, tell nobody.", "Demands a UPI 'security deposit'."];
  return h(
    "div",
    { class: "scene" },
    h(
      "div",
      { class: "sc-card card" },
      h("div", { class: "sc-head" }, h("span", { class: "tag" }, "Strain captured"), h("small", {}, "identifiers removed")),
      h("h3", { class: "sc-title" }, "Digital arrest"),
      h("ol", { class: "sc-steps" }, steps.map((s, i) => h("li", { style: { "--i": i } }, h("b", {}, String(i + 1)), s))),
      h("div", { class: "chips" }, ["Fear and urgency", "Secrecy", "Personal UPI ID"].map((t) => h("span", { class: "chip danger" }, icon("alert"), t))),
      h("div", { class: "sc-redact" }, h("i"), h("i"), h("i")),
    ),
  );
}

function sceneVaccine() {
  return h(
    "div",
    { class: "scene" },
    h(
      "div",
      { class: "sc-card card sc-vac" },
      h("div", { class: "sc-shield" }, icon("shield")),
      h("h3", { class: "sc-title" }, "Practice call with Dadaji"),
      h("p", { class: "muted", lang: "en" }, "The coach plays the scammer. At the first digit of an OTP it cuts in, kindly."),
      h("div", { class: "sc-chip" }, icon("heart"), h("div", {}, h("small", {}, "Coach stopped the call"), h("b", {}, "Before any detail was shared")), h("span", { class: "badge ok" }, "Passed")),
    ),
  );
}

function story() {
  const steps = [
    { n: "01", title: "Trap", text: "The decoy picks up and keeps the scammer talking. Every account number, UPI ID, link and name they say is caught, double-checked and timestamped.", href: "#/call", cta: "Try a call" },
    { n: "02", title: "Strain", text: "Each call is distilled into a redacted card of how this scam works, step by step, with no personal identifiers left in it.", href: "#/strains", cta: "See strains" },
    { n: "03", title: "Vaccine", text: "Turn a strain into a short, consented practice call for a parent or grandparent. The coach stops them the moment they would have shared a detail.", href: "#/drills", cta: "Family drills" },
  ];
  const copies = steps.map((s, i) =>
    h("article", { class: "story-copy", "data-i": i }, h("span", { class: "story-n" }, s.n), h("h2", {}, s.title), h("p", { class: "lead" }, s.text), link(s.href, "btn ghost", s.cta, icon("arrow"))),
  );
  const rails = steps.map((s, i) => h("button", { class: "story-rail", type: "button", "aria-label": `Step ${i + 1}: ${s.title}`, onClick: () => control.goTo(i) }, h("i"), s.title));
  const scenes = [sceneTrap(), sceneStrain(), sceneVaccine()];
  scenes.forEach((scene, i) => scene.setAttribute("data-i", i));
  const el = h(
    "section",
    { class: "story", "data-step": "0" },
    h(
      "div",
      { class: "story-sticky" },
      h("div", { class: "story-head" }, h("span", { class: "eyebrow" }, "How it works"), h("div", { class: "story-rails" }, rails), h("div", { class: "story-bar", "aria-hidden": "true" }, h("i"))),
      h("div", { class: "story-grid" }, h("div", { class: "story-copies" }, copies), h("div", { class: "story-stage" }, scenes)),
    ),
  );
  const control = pinnedStory(el, steps.length, rails);
  return { el, destroy: control.destroy };
}

export function HomeView() {
  const stage = heroStage();
  const hero = h(
    "section",
    { class: "hero" },
    h(
      "div",
      { class: "hero-text" },
      h("span", { class: "eyebrow-pill reveal" }, icon("zap"), "AI Builder Cup 2026 · built on Google Cloud"),
      h("h1", { "data-split": "now" }, "Let the scammer talk to ", h("span", { class: "grad-text" }, "someone who is never going to pay.")),
      h(
        "p",
        { class: "lead reveal" },
        `${BRAND.name} is an AI decoy that answers scam calls in English, हिन्दी and Hinglish. It plays a worried 68-year-old, wastes the scammer's time, quietly collects the UPI IDs and bank details they ask you to pay, and saves the call as evidence.`,
      ),
      h(
        "div",
        { class: "cta-row reveal" },
        link("#/call", "btn primary lg", icon("phone"), "Take a live call"),
        link("#/replay", "btn lg", icon("play"), "Watch a replay"),
        link("#/chat", "btn ghost lg", icon("chat"), "Chat instead"),
      ),
      h("ul", { class: "trust reveal" }, ["Free, no sign-up", "Private recordings", "Fictional persona and data"].map((t) => h("li", {}, icon("check"), t))),
    ),
    stage.el,
    h("div", { class: "scroll-cue", "aria-hidden": "true" }, h("i"), "Scroll"),
  );

  const tick = ticker();
  const stopTicker = velocityMarquee(tick.track, { speed: 46 });

  const stat = (value, label, sub, formatter) => {
    const num = h("b", { class: "stat-n" }, "0");
    const cell = h("div", { class: "stat-cell reveal" }, num, h("span", {}, label), sub ? h("small", {}, sub) : null);
    cell._count = () => countUp(num, value, { format: formatter });
    return cell;
  };
  const stats = [
    stat(22495, "crore rupees reported lost to cyber fraud in 2025", "Source: National Cybercrime Reporting Portal (NCRP) data", (n) => `₹${Math.round(n).toLocaleString("en-IN")}`),
    stat(3, "languages understood on the line", "English, Hindi and Hinglish", (n) => String(Math.round(n))),
    stat(2, "independent checks before a detail counts as confirmed", "A live tool call plus a second AI pass", (n) => String(Math.round(n))),
  ];
  const statsBand = h("section", { class: "stats-band" }, stats);
  const io = "IntersectionObserver" in window ? new IntersectionObserver((entries) => entries.forEach((e) => e.isIntersecting && (e.target._count?.(), io.unobserve(e.target))), { threshold: 0.4 }) : null;
  stats.forEach((cell) => (io ? io.observe(cell) : cell._count()));

  const pinned = story();

  const tryIt = h(
    "section",
    { class: "section two-col" },
    h(
      "div",
      { class: "reveal" },
      h("span", { class: "eyebrow" }, "Try it in a minute"),
      h("h2", { "data-split": "" }, "You play the scammer. The AI plays the victim."),
      h("p", { class: "muted" }, "Open the live call, allow the microphone and read one of these lines. Ramesh answers in the language you speak, repeats numbers back slowly, and the dashboard fills in as you talk. No microphone? Send the lines as text."),
      h("div", { class: "cta-row" }, link("#/call", "btn primary", icon("mic"), "Start the live call"), link("#/chat", "btn", icon("chat"), "Use text chat")),
    ),
    h("div", { class: "reveal" }, scriptPanel({ title: "Sample scam script" })),
  );

  const promise = (ico, title, text) => h("div", { class: "promise reveal" }, h("div", { class: "promise-i" }, icon(ico)), h("div", {}, h("h4", {}, title), h("p", { class: "muted" }, text)));
  const trust = h(
    "section",
    { class: "section" },
    h("div", { class: "section-h reveal" }, h("span", { class: "eyebrow" }, "Built to be safe"), h("h2", { "data-split": "" }, "A decoy with firm limits.")),
    h(
      "div",
      { class: "grid three" },
      promise("lock", "Never real data", "Ramesh is fictional and so is everything he says about himself. He never hands over an OTP, PIN, CVV, password or card number, and he never claims to be anything but a retired schoolteacher."),
      promise("shield", "A lead, not a verdict", "Evidence packs say plainly that details were heard from an unverified caller and may be mis-heard. They help investigators, they do not accuse anyone."),
      promise("heart", "Consent first", "Family drills only start after the family member agrees. Nothing real is ever asked, and the coach stops the call at the first sign of risk."),
    ),
  );

  const finale = h(
    "section",
    { class: "finale reveal" },
    h("span", { class: "eyebrow center" }, "See the whole loop in under five minutes"),
    h("h2", { "data-split": "" }, "Make them ", h("span", { class: "grad-text" }, "wait.")),
    h(
      "div",
      { class: "cta-row center" },
      link("#/call", "finale-btn mag", icon("phone"), h("span", {}, "Take a live call")),
      link("#/replay", "btn lg", icon("play"), "Watch the replay"),
    ),
  );

  const el = h("div", { class: "home" }, hero, tick.el, statsBand, pinned.el, marquee(), tryIt, trust, finale);

  let queued = false;
  const onScroll = () => {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      hero.style.setProperty("--sy", Math.min(1.2, window.scrollY / Math.max(1, window.innerHeight)).toFixed(3));
    });
  };
  window.addEventListener("scroll", onScroll, { passive: true });

  queueMicrotask(() => {
    observeReveal(el);
    initSplit(el);
  });
  return {
    el,
    destroy() {
      io?.disconnect();
      stopTicker();
      pinned.destroy();
      stage.destroy();
      window.removeEventListener("scroll", onScroll);
    },
  };
}
