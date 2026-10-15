import { BRAND } from "../brand.js";
import { scriptPanel } from "../scripts.js";
import { SCAM_LABELS, countUp, h, icon, observeReveal } from "../util.js";

const link = (href, cls, ...children) => h("a", { href, class: cls }, ...children);

function marquee() {
  const labels = Object.entries(SCAM_LABELS).filter(([id]) => id !== "not_scam").map(([, label]) => label);
  const row = () => labels.map((label) => h("span", { class: "mq-item" }, h("i"), label));
  return h(
    "section",
    { class: "marquee reveal" },
    h("p", { class: "eyebrow marquee-label center" }, "Scam strains it recognises"),
    h("div", { class: "marquee-track", "aria-hidden": "true" }, row(), row()),
  );
}

function heroMock() {
  const bubble = (who, text, cls, delay) => h("div", { class: `mock-bubble ${cls}`, style: { "--d": `${delay}s` } }, h("small", {}, who), h("p", { lang: "en" }, text));
  const chip = (ico, label, value, delay, cls = "") => h("div", { class: `mock-chip ${cls}`, style: { "--d": `${delay}s` } }, icon(ico), h("div", {}, h("small", {}, label), h("b", {}, value)));
  return h(
    "div",
    { class: "hero-mock tilt", "aria-hidden": "true" },
    h(
      "div",
      { class: "mock-phone card" },
      h(
        "div",
        { class: "mock-head" },
        h("span", { class: "mock-orb" }, "RS"),
        h("div", {}, h("b", {}, "Ramesh Sharma, 68"), h("small", {}, "decoy on the line · 02:47")),
        h("span", { class: "live-dot" }, "LIVE"),
      ),
      h("div", { class: "mock-wave" }, Array.from({ length: 28 }, (_, i) => h("i", { style: { "--i": i } }))),
      h(
        "div",
        { class: "mock-chat" },
        bubble("Caller", "A parcel in your name has illegal items. Pay 50,000 now.", "caller", 0.4),
        bubble("Ramesh", "Which parcel, sir? I never ordered anything... say the UPI ID slowly.", "persona", 2.4),
        bubble("Caller", "rahul dot sharma at okaxis.", "caller", 4.6),
      ),
    ),
    chip("card", "UPI ID caught", "rahul.sharma@okaxis", 5.8, "c1"),
    chip("shield", "Scam type", "Digital arrest · 94%", 3.2, "c2"),
    chip("clock", "Scammer's time wasted", "02:47 and counting", 1.2, "c3"),
  );
}

export function HomeView() {
  const hero = h(
    "section",
    { class: "hero" },
    h(
      "div",
      { class: "hero-text" },
      h("span", { class: "eyebrow-pill reveal" }, icon("zap"), "AI Builder Cup 2026 · built on Google Cloud"),
      h("h1", { class: "reveal" }, "Let the scammer talk to ", h("span", { class: "grad-text" }, "someone who is never going to pay.")),
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
    heroMock(),
  );

  const stat = (value, label, sub, formatter, big = false) => {
    const num = h("b", { class: "stat-n" }, "0");
    const card = h("div", { class: `big-stat card reveal ${big ? "wide" : ""}` }, num, h("span", {}, label), sub ? h("small", {}, sub) : null);
    card._count = () => countUp(num, value, { format: formatter });
    return card;
  };
  const stats = [
    stat(22495, "crore rupees reported lost to cyber fraud in 2025", "Source: National Cybercrime Reporting Portal (NCRP) data", (n) => `₹${Math.round(n).toLocaleString("en-IN")}`, true),
    stat(3, "languages understood on the line", "English, Hindi and Hinglish", (n) => String(Math.round(n))),
    stat(2, "independent checks before a detail counts as confirmed", "A live tool call plus a second AI pass", (n) => String(Math.round(n))),
  ];
  const statsBand = h("section", { class: "stats-band" }, stats);
  const io = "IntersectionObserver" in window ? new IntersectionObserver((entries) => entries.forEach((e) => e.isIntersecting && (e.target._count?.(), io.unobserve(e.target))), { threshold: 0.4 }) : null;
  stats.forEach((card) => (io ? io.observe(card) : card._count()));

  const step = (n, ico, title, text, href, cta) =>
    h("article", { class: "card step-card reveal" }, h("div", { class: "step-n" }, n), h("div", { class: "step-i" }, icon(ico)), h("h3", {}, title), h("p", { class: "muted" }, text), link(href, "btn ghost", cta, icon("arrow")));
  const pipeline = h(
    "section",
    { class: "section" },
    h("div", { class: "section-h reveal" }, h("span", { class: "eyebrow" }, "How it works"), h("h2", {}, "Trap. Strain. Vaccine.")),
    h(
      "div",
      { class: "grid three" },
      step("1", "phone", "Trap", "The decoy picks up and keeps the scammer talking. Every account number, UPI ID, link and name they say is caught, double-checked and timestamped.", "#/call", "Try a call"),
      step("2", "virus", "Strain", "Each call is distilled into a redacted card of how this scam works, step by step, with no personal identifiers left in it.", "#/strains", "See strains"),
      step("3", "users", "Vaccine", "Turn a strain into a short, consented practice call for a parent or grandparent. The coach stops them the moment they would have shared a detail.", "#/drills", "Family drills"),
    ),
  );

  const tryIt = h(
    "section",
    { class: "section two-col" },
    h(
      "div",
      { class: "reveal" },
      h("span", { class: "eyebrow" }, "Try it in a minute"),
      h("h2", {}, "You play the scammer. The AI plays the victim."),
      h("p", { class: "muted" }, "Open the live call, allow the microphone and read one of these lines. Ramesh answers in the language you speak, repeats numbers back slowly, and the dashboard fills in as you talk. No microphone? Send the lines as text."),
      h("div", { class: "cta-row" }, link("#/call", "btn primary", icon("mic"), "Start the live call"), link("#/chat", "btn", icon("chat"), "Use text chat")),
    ),
    h("div", { class: "reveal" }, scriptPanel({ title: "Sample scam script" })),
  );

  const promise = (ico, title, text) => h("div", { class: "promise reveal" }, h("div", { class: "promise-i" }, icon(ico)), h("div", {}, h("h4", {}, title), h("p", { class: "muted" }, text)));
  const trust = h(
    "section",
    { class: "section" },
    h("div", { class: "section-h reveal" }, h("span", { class: "eyebrow" }, "Built to be safe"), h("h2", {}, "A decoy with firm limits.")),
    h(
      "div",
      { class: "grid three" },
      promise("lock", "Never real data", "Ramesh is fictional. He never reveals real personal, bank, Aadhaar, OTP or card details, and he never claims to be anything but a worried old man."),
      promise("shield", "A lead, not a verdict", "Evidence packs say plainly that details were heard from an unverified caller and may be mis-heard. They help investigators, they do not accuse anyone."),
      promise("heart", "Consent first", "Family drills only start after the family member agrees. Nothing real is ever asked, and the coach stops the call at the first sign of risk."),
    ),
  );

  const footerCta = h(
    "section",
    { class: "final-cta card reveal" },
    h("h2", {}, "See the whole loop in under five minutes."),
    h("p", { class: "muted" }, "Start with the replay if you want to see it without a microphone."),
    h("div", { class: "cta-row center" }, link("#/replay", "btn lg", icon("play"), "Watch the replay"), link("#/call", "btn primary lg", icon("phone"), "Take a live call")),
  );

  const el = h("div", { class: "home" }, hero, marquee(), statsBand, pipeline, tryIt, trust, footerCta);
  queueMicrotask(() => observeReveal(el));
  return { el, destroy: () => io?.disconnect() };
}
