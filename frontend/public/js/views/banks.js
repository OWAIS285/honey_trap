// Proxy bank inboxes: which banks received mule-account reports from this browser's calls, and what each bank sees.

import { api } from "../api.js";
import { backLink, emptyState, errorState, pageHeader, skeletons } from "../components.js";
import { BANK_DECISIONS, DELIVERY_LABELS, DETAIL_META, ROUTED_BY_LABELS, bankItemState, fmtDate, pct, h, humanize, icon, observeReveal, scamLabel, toast } from "../util.js";

const INTRO =
  "Every UPI ID or account number from a scam call gets a confidence score (how sure we are the call is a scam x how sure we caught the detail right). At 65% or more it is routed to the bank that can act on it and a signed report is delivered at once. Between 45% and 65% it waits on the watchlist; every later call that gives the same detail raises the score. These inboxes are proxies; nothing is sent to an actual bank.";

export function BanksView() {
  const el = h("div", { class: "page" }, pageHeader("Bank inboxes", INTRO), skeletons(3));

  async function load() {
    let data;
    let watch;
    try {
      [data, watch] = await Promise.all([api.banks(), api.watchlist()]);
    } catch (err) {
      el.replaceChildren(pageHeader("Bank inboxes"), errorState(err.message, load));
      return;
    }
    const watchCard = watchlistCard(watch);
    const withReports = data.banks.filter((b) => b.reports > 0);
    const header = pageHeader("Bank inboxes", INTRO);
    if (!withReports.length) {
      el.replaceChildren(
        header,
        emptyState({
          iconName: "bank",
          title: "No reports yet",
          text: "Take a call as a scammer and give Ramesh a UPI ID or an account number with its IFSC. Once the call is judged a scam and the detail is confirmed, the report lands in that bank's inbox here.",
          action: h("a", { class: "btn primary", href: "#/call" }, icon("phone"), "Take a call"),
        }),
        watchCard,
        bankDirectory(data.banks),
      );
      observeReveal(el);
      return;
    }
    const cards = withReports.map((b) =>
      h(
        "a",
        { class: "card call-card reveal", href: `#/banks/${b.code}` },
        h(
          "div",
          { class: "cc-top" },
          h("span", { class: "cc-icon" }, icon(b.code === "UNRESOLVED" ? "alert" : "bank")),
          h("div", {}, h("h3", {}, b.name), h("small", { class: "muted" }, b.code === "UNRESOLVED" ? "Manual triage queue" : `IFSC prefix ${b.code}`)),
          h("span", { class: "grow" }),
          h("span", { class: "chip ok" }, `${b.reports} report${b.reports === 1 ? "" : "s"}`),
        ),
      ),
    );
    el.replaceChildren(header, h("div", { class: "grid cards" }, cards), watchCard, apiNote(data.apiEnabled), bankDirectory(data.banks));
    observeReveal(el);
  }

  load();
  return { el };
}

function watchlistCard({ items, reportAt }) {
  if (!items.length) return null;
  const rows = items.map((item) => {
    const meta = DETAIL_META[item.type] || { label: humanize(item.type), icon: "hash" };
    const state = bankItemState(item);
    const fill = Math.min(100, Math.round(((item.confidence || 0) / reportAt) * 100));
    return h(
      "article",
      { class: "ev-row" },
      h(
        "div",
        { class: "ev-head" },
        h("span", { class: "ev-type" }, icon(item.stage === "reported" ? "bank" : "eye"), meta.label),
        h("span", { class: `badge ${state.tone}` }, state.label),
        h("span", { class: "chip" }, `${item.sightings} call${item.sightings === 1 ? "" : "s"}`),
        h("span", { class: "grow" }),
        item.bankName ? h("small", { class: "muted" }, item.bankName) : h("small", { class: "muted" }, "bank not known yet"),
      ),
      h("div", { class: "ev-value mono" }, item.value),
      h("div", { class: "watch-bar", title: `${pct(item.confidence)} of the ${pct(reportAt)} needed` }, h("i", { style: `width:${fill}%` })),
      h("small", { class: "muted" }, item.stage === "reported" ? `${pct(item.confidence)} confidence, reported to the bank.` : `${pct(item.confidence)} confidence. Reported automatically at ${pct(reportAt)}, if another call gives it again.`),
    );
  });
  return h(
    "section",
    { class: "card section-gap reveal" },
    h("div", { class: "card-h" }, icon("eye"), "Watchlist from your calls"),
    h("p", { class: "muted" }, "Details from your scam calls that were not certain enough to report on their own, and what happened to them."),
    h("div", { class: "ev-list" }, rows),
  );
}

function apiNote(enabled) {
  return h(
    "section",
    { class: "card section-gap reveal" },
    h("div", { class: "card-h" }, icon("lock"), "How a bank connects"),
    h(
      "ul",
      { class: "plain-list" },
      h("li", {}, "Push: each report is POSTed to the bank's webhook with an HMAC-SHA256 signature (X-Stallwart-Signature), a timestamp and an idempotency key, retried on failure."),
      h("li", {}, "Pull: GET /bank-api/v1/{IFSC prefix}/reports and /mule-accounts with the bank's X-Bank-Key. Every account is de-duplicated across calls with a sighting count."),
      h("li", {}, "Feedback: POST /bank-api/v1/{IFSC prefix}/mule-accounts/{key}/status with monitoring, frozen or dismissed; the decision rides on every later report of that account."),
      h("li", {}, enabled ? "The bank API is switched on for this server." : "The bank API is switched off on this server (no signing secret configured); the webhook flow still runs."),
    ),
  );
}

function bankDirectory(banks) {
  const known = banks.filter((b) => b.code !== "UNRESOLVED");
  return h(
    "details",
    { class: "card section-gap reveal" },
    h("summary", {}, `Banks we can route to (${known.length})`),
    h("div", { class: "chips" }, known.map((b) => h("a", { class: "chip action", href: `#/banks/${b.code}`, title: `IFSC prefix ${b.code}` }, b.name))),
  );
}

export function BankInboxView({ code }) {
  const back = backLink("#/banks", "All bank inboxes");
  const el = h("div", { class: "page" }, back, pageHeader("Bank inbox", "Loading…"), skeletons(2));

  async function load() {
    let data;
    try {
      data = await api.bankReports(code);
    } catch (err) {
      el.replaceChildren(back, pageHeader("Bank inbox"), errorState(err.status === 404 ? "There is no such bank." : err.message, err.status === 404 ? null : load));
      return;
    }
    const { bank, reports } = data;
    const subtitle =
      bank.code === "UNRESOLVED"
        ? "Details we could not tie to a bank (an account number with no IFSC, an unknown UPI handle). In production these go to NPCI or I4C for a lookup."
        : `Proxy inbox for ${bank.name} (IFSC prefix ${bank.code}). Showing reports from your own calls; a bank sees every call's reports through the bank API.`;
    if (!reports.length) {
      el.replaceChildren(back, pageHeader(bank.name, subtitle), emptyState({ iconName: "bank", title: "Inbox empty", text: "No report from your calls has been routed to this bank yet." }));
      observeReveal(el);
      return;
    }
    el.replaceChildren(back, pageHeader(bank.name, subtitle), h("div", { class: "ev-list section-gap" }, reports.map((r) => reportRow(bank, r))));
    observeReveal(el);
  }

  function reportRow(bank, r) {
    const meta = DETAIL_META[r.detailType] || { label: humanize(r.detailType), icon: "hash" };
    const decision = r.bankStatus !== "reported" ? r.bankStatus : r.simulatedDecision || "reported";
    const status = BANK_DECISIONS[decision] || BANK_DECISIONS.reported;
    const statusBadge = h("span", { class: `badge ${status.tone}` }, status.label);
    const confidence = r.currentConfidence ?? r.confidence;
    const buttons = bank.code === "UNRESOLVED"
      ? null
      : h(
          "div",
          { class: "cta-row" },
          ["monitoring", "frozen", "dismissed"].map((d) =>
            h("button", { class: `btn sm ${d === "frozen" ? "danger" : ""}`, type: "button", onClick: () => decide(r, d, statusBadge) }, d === "frozen" ? "Freeze" : d === "monitoring" ? "Monitor" : "Dismiss"),
          ),
        );
    return h(
      "article",
      { class: "card ev-row reveal" },
      h(
        "div",
        { class: "ev-head" },
        h("span", { class: "ev-type" }, icon(meta.icon), meta.label),
        h("span", { class: `badge ${r.status === "delivered" ? "ok" : r.status === "failed" ? "bad" : "warn"}` }, DELIVERY_LABELS[r.status] || r.status),
        statusBadge,
        r.recommendedAction === "review_for_freeze" ? h("span", { class: "chip danger" }, "Review for freeze") : h("span", { class: "chip" }, "Monitor"),
        confidence != null ? h("span", { class: "chip ok" }, `${pct(confidence)} confidence`) : null,
        h("span", { class: "grow" }),
        h("small", { class: "muted" }, fmtDate(r.sentAt)),
      ),
      h("div", { class: "ev-value mono" }, r.value),
      h(
        "div",
        { class: "chips" },
        h("span", { class: "chip" }, ROUTED_BY_LABELS[r.routedBy] || r.routedBy),
        r.scamType ? h("span", { class: "chip" }, scamLabel(r.scamType)) : null,
        h("span", { class: `chip ${r.sightings > 1 ? "danger" : ""}` }, `seen in ${r.sightings} call${r.sightings === 1 ? "" : "s"}`),
        r.callId ? h("a", { class: "chip action", href: `#/call/${r.callId}` }, icon("file"), "Source call") : null,
      ),
      r.routingReason ? h("small", { class: "muted" }, r.routingReason) : null,
      (r.linkedDetails || []).length
        ? h("small", { class: "muted" }, "Same caller also gave: ", (r.linkedDetails || []).map((l) => `${humanize(l.type)} ${l.value || `${l.valueMasked} (${l.bank || "unknown bank"})`}`).join(" · "))
        : null,
      buttons ? h("div", {}, h("small", { class: "muted" }, "Play the bank (demo only, recorded on your copy of the report):"), buttons) : null,
    );
  }

  async function decide(report, decision, badge) {
    try {
      await api.bankDecision(code, report.reportId, decision);
      const status = BANK_DECISIONS[decision];
      badge.className = `badge ${status.tone}`;
      badge.textContent = status.label;
      toast(`Marked as ${status.label.toLowerCase()}.`, "ok");
    } catch (err) {
      toast(err.message, "error");
    }
  }

  load();
  return { el };
}
