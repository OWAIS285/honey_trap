// Small DOM helpers, icons, labels and formatters shared by every view.
// All dynamic text is inserted with textContent (never innerHTML) so transcripts cannot inject markup.

export function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "style" && typeof value === "object") {
      for (const [name, v] of Object.entries(value)) {
        if (name.startsWith("--")) el.style.setProperty(name, String(v));
        else el.style[name] = v;
      }
    }
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (["value", "checked", "disabled", "selected", "hidden"].includes(key)) el[key] = value;
    else el.setAttribute(key, value === true ? "" : value);
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

export function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
  return el;
}

export const $ = (selector, root = document) => root.querySelector(selector);

// ---------- icons (static markup only) ----------

const ICONS = {
  phone: '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
  hangup: '<path d="M10.68 13.31a16 16 0 0 0 3.41 2.6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7 2 2 0 0 1 1.72 2v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.42 19.42 0 0 1-3.33-2.67m-2.67-3.34a19.79 19.79 0 0 1-3.07-8.63A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91"/><line x1="23" y1="1" x2="1" y2="23"/>',
  mic: '<path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>',
  micoff: '<line x1="1" y1="1" x2="23" y2="23"/><path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"/><path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/>',
  chat: '<path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/>',
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  pause: '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  printer: '<polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  alert: '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  send: '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>',
  home: '<path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
  globe: '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
  hash: '<line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/>',
  smartphone: '<rect x="5" y="2" width="14" height="20" rx="2" ry="2"/><line x1="12" y1="18" x2="12.01" y2="18"/>',
  bank: '<path d="M3 21h18"/><path d="M5 21V10"/><path d="M9 21V10"/><path d="M15 21V10"/><path d="M19 21V10"/><path d="M12 3L2 9h20z"/>',
  card: '<rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/>',
  arrow: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
  back: '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>',
  virus: '<circle cx="12" cy="12" r="4"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4M4.9 4.9l2.8 2.8M16.3 16.3l2.8 2.8M4.9 19.1l2.8-2.8M16.3 7.7l2.8-2.8"/>',
  zap: '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
  volume: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
  rupee: '<path d="M6 3h12"/><path d="M6 8h12"/><path d="M6 13h4a4 4 0 0 0 0-10"/><path d="M6 13l8.5 8"/>',
  building: '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01M12 6h.01M16 6h.01M8 10h.01M12 10h.01M16 10h.01M8 14h.01M12 14h.01M16 14h.01"/>',
  badge: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M15 8h2M15 12h2M7 16h10"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  rewind: '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
  skip: '<polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  heart: '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>',
  trend: '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/>',
};

export function icon(name, size) {
  const holder = document.createElement("template");
  holder.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
  const svg = holder.content.firstChild;
  if (size) {
    svg.setAttribute("width", size);
    svg.setAttribute("height", size);
  }
  return svg;
}

export function logo() {
  const holder = document.createElement("template");
  holder.innerHTML =
    '<svg viewBox="0 0 40 40" aria-hidden="true"><defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1d4ed8"/><stop offset="1" stop-color="#38bdf8"/></linearGradient></defs>' +
    '<rect x="2" y="2" width="36" height="36" rx="12" fill="url(#lg)"/>' +
    '<g fill="#fff"><rect x="8.4" y="16" width="3.2" height="8" rx="1.6"/><rect x="13.7" y="11" width="3.2" height="18" rx="1.6"/><rect x="19" y="7" width="3.2" height="26" rx="1.6"/><rect x="24.3" y="13" width="3.2" height="14" rx="1.6"/><rect x="29.6" y="16" width="3.2" height="8" rx="1.6"/></g></svg>';
  return holder.content.firstChild;
}

// ---------- labels ----------

export const DETAIL_META = {
  upi_id: { label: "UPI ID", icon: "card" },
  bank_account: { label: "Bank account", icon: "bank" },
  ifsc: { label: "IFSC code", icon: "bank" },
  phone_number: { label: "Phone number", icon: "phone" },
  url: { label: "Link", icon: "link" },
  app_name: { label: "App asked to install", icon: "smartphone" },
  person_name: { label: "Name used", icon: "user" },
  organisation_claimed: { label: "Organisation claimed", icon: "building" },
  case_or_badge_id: { label: "Case / badge ID", icon: "badge" },
  amount_demanded: { label: "Amount demanded", icon: "rupee" },
};

export const SCAM_LABELS = {
  digital_arrest: "Digital arrest",
  courier_parcel: "Courier / parcel",
  telecom_trai_sim_block: "TRAI / SIM block",
  bank_kyc_block: "Bank KYC block",
  electricity_bill: "Electricity bill",
  investment_trading: "Investment / trading",
  task_job: "Task / job",
  lottery_prize: "Lottery / prize",
  fake_customer_care: "Fake customer care",
  family_emergency: "Family emergency",
  loan_app: "Loan app",
  other_scam: "Other scam",
  not_scam: "Not a scam",
  undetermined: "Not clear yet",
};

export const STAGES = [
  { id: "hook", label: "Hook" },
  { id: "fear", label: "Fear" },
  { id: "isolation", label: "Isolation" },
  { id: "payment_demand", label: "Payment demand" },
  { id: "escalation", label: "Escalation" },
];

export const SOURCE_LABELS = { live_tool: "heard live", verifier: "second check" };

// Short names for the behaviours that decide the verdict (the server sends the full definition and the quote).
export const SIGNAL_LABELS = {
  asks_secret_credential: "Asked for OTP / PIN / password",
  remote_access_or_install: "Asked to install an app",
  pay_to_receive: "Pay first to receive",
  payment_to_personal_account: "Money to a personal account",
  arrest_or_legal_threat: "Threat of arrest or case",
  secrecy_or_isolation: "Told to keep it secret",
  extortion_threat: "Threat to shame or harm",
  urgency_deadline: "Threatening deadline",
  discourages_verification: "Refused a callback",
  asks_full_identifier: "Wanted a full ID number",
  link_or_unofficial_channel: "Link or unofficial channel",
  too_good_to_be_true: "Too good to be true",
  emotional_emergency: "Family emergency pressure",
  identity_inconsistency: "Story does not add up",
  offers_official_verification: "Offered official callback",
  partial_identifier_only: "Asked only partial details",
  official_channel_only: "Official channel only",
  accepts_refusal: "Accepted a no",
  no_request: "Asked for nothing",
  knows_customer_record: "Knew his account's last 4 digits",
};

export const ROUTED_BY_LABELS = {
  ifsc: "by IFSC",
  upi_handle: "by UPI handle",
  bank_named: "by bank name",
  unresolved: "needs a manual lookup",
};

export const BANK_DECISIONS = {
  reported: { label: "Reported", tone: "" },
  monitoring: { label: "Monitoring", tone: "warn" },
  frozen: { label: "Frozen", tone: "bad" },
  dismissed: { label: "Dismissed", tone: "" },
};

export const DELIVERY_LABELS = { pending: "Sending…", delivered: "Delivered", failed: "Delivery failed" };

export const pct = (x) => `${Math.round((x || 0) * 100)}%`;

/** One line for a tracked UPI ID or account: reported to a bank, or held on the watchlist below the report level. */
export function bankItemState(item) {
  if (item.stage === "reported" && item.status) {
    const tone = item.status === "delivered" ? "ok" : item.status === "failed" ? "bad" : "warn";
    return { tone, label: DELIVERY_LABELS[item.status] || item.status };
  }
  if (item.stage === "reported") return { tone: "ok", label: "Reported" };
  return { tone: "warn", label: "On watch" };
}

export const VERDICT_LABELS = { scam: "Scam", legitimate: "Not a scam", undetermined: "Not clear yet" };

export const verdictTitle = (verdict, scamType) => (verdict === "scam" ? scamLabel(scamType) : VERDICT_LABELS[verdict] || scamLabel(scamType));

export const scamLabel = (id) => SCAM_LABELS[id] || (id ? humanize(id) : "Listening…");

export function humanize(text) {
  return String(text || "").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

// ---------- formatters ----------

export function fmtClock(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function fmtDuration(seconds) {
  const s = Math.round(seconds || 0);
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

// ---------- feedback ----------

export function toast(message, kind = "info", ms = 4200) {
  const host = document.getElementById("toasts");
  if (!host) return;
  const item = h("div", { class: `toast ${kind}`, role: "status" }, icon(kind === "error" ? "alert" : "check"), h("span", {}, message));
  host.append(item);
  setTimeout(() => {
    item.classList.add("out");
    setTimeout(() => item.remove(), 400);
  }, ms);
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copied to clipboard", "ok", 2000);
  } catch {
    toast("Could not copy. Select the text and copy it manually.", "error");
  }
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = h("a", { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

// ---------- motion helpers ----------

export const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function countUp(el, to, { duration = 1400, format = (n) => String(Math.round(n)) } = {}) {
  if (reducedMotion()) {
    el.textContent = format(to);
    return;
  }
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = format(to * eased);
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

let revealObserver;
export function observeReveal(root) {
  const items = root.querySelectorAll(".reveal:not(.in)");
  if (!("IntersectionObserver" in window) || reducedMotion()) {
    items.forEach((el) => el.classList.add("in"));
    return;
  }
  revealObserver ||= new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add("in");
          revealObserver.unobserve(entry.target);
        }
      }
    },
    { threshold: 0.12 },
  );
  items.forEach((el, i) => {
    el.style.setProperty("--d", `${(i % 6) * 70}ms`);
    revealObserver.observe(el);
  });
}

/** Move a node to a new parent and animate it from its old position (FLIP). */
export function flipMove(node, newParent, before = null) {
  const first = node.getBoundingClientRect();
  newParent.insertBefore(node, before);
  if (reducedMotion() || !node.animate) return;
  const last = node.getBoundingClientRect();
  const dx = first.left - last.left;
  const dy = first.top - last.top;
  node.animate(
    [{ transform: `translate(${dx}px, ${dy}px) scale(.98)` }, { transform: "translate(0, 0) scale(1)" }],
    { duration: 520, easing: "cubic-bezier(.2,.9,.2,1)" },
  );
}

/** Ripple on every .btn press. */
export function installRipples() {
  document.addEventListener("pointerdown", (event) => {
    const btn = event.target.closest?.(".btn");
    if (!btn || reducedMotion()) return;
    const rect = btn.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 1.6;
    const ripple = h("span", { class: "ripple" });
    ripple.style.width = ripple.style.height = `${size}px`;
    ripple.style.left = `${event.clientX - rect.left - size / 2}px`;
    ripple.style.top = `${event.clientY - rect.top - size / 2}px`;
    btn.append(ripple);
    setTimeout(() => ripple.remove(), 650);
  });
}
