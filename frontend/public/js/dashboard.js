// Live analysis dashboard: scam-type gauge, script stage, caught details (confirmed vs heard) and transcript.
// It only consumes server events, so the same component drives live calls, chat and the replay.

import { DETAIL_META, ROUTED_BY_LABELS, bankItemState, pct, SIGNAL_LABELS, SOURCE_LABELS, STAGES, clear, flipMove, fmtClock, h, humanize, icon, scamLabel, verdictTitle } from "./util.js";

const CIRCUMFERENCE = 2 * Math.PI * 52;

export function createDashboard({ callerLabel = "Caller", personaLabel = "Ramesh" } = {}) {
  const details = new Map(); // id -> { data, node }
  const liveBubbles = {};
  let clockStart = null;
  let clockTimer = null;
  let lastTone = "idle";

  // ----- gauge -----
  const gaugeSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  gaugeSvg.setAttribute("viewBox", "0 0 120 120");
  const track = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  track.setAttribute("class", "g-track");
  for (const [k, v] of Object.entries({ cx: 60, cy: 60, r: 52 })) track.setAttribute(k, v);
  const fill = document.createElementNS("http://www.w3.org/2000/svg", "circle");
  fill.setAttribute("class", "g-fill");
  for (const [k, v] of Object.entries({ cx: 60, cy: 60, r: 52 })) fill.setAttribute(k, v);
  fill.setAttribute("stroke-dasharray", String(CIRCUMFERENCE));
  fill.setAttribute("stroke-dashoffset", String(CIRCUMFERENCE));
  gaugeSvg.append(track, fill);

  const pctEl = h("b", { class: "g-pct" }, "0%");
  const typeEl = h("h3", { class: "g-type" }, "Listening…");
  const entityEl = h("div", { class: "g-entity" }, "Waiting for the caller to say something.");
  const triggersEl = h("div", { class: "chips g-triggers" });
  const gaugeCard = h(
    "section",
    { class: "card gauge-card", "data-tone": "idle" },
    h("div", { class: "gauge" }, gaugeSvg, h("div", { class: "gauge-center" }, pctEl, h("span", {}, "confidence"))),
    h("div", { class: "gauge-info" }, h("div", { class: "eyebrow" }, "Scam type"), typeEl, entityEl, triggersEl),
  );

  // ----- stage stepper -----
  const stageNodes = STAGES.map((stage, i) =>
    h("li", { class: "step", "data-stage": stage.id }, h("span", { class: "dot" }, String(i + 1)), h("span", { class: "lbl" }, stage.label)),
  );
  const stageCard = h(
    "section",
    { class: "card stage-card" },
    h("div", { class: "eyebrow" }, "Where the caller is in the script"),
    h("ol", { class: "stepper" }, stageNodes),
  );

  // ----- stats -----
  const clockEl = h("b", {}, "00:00");
  const detailsStat = h("b", {}, "0");
  const detailsSub = h("small", {}, "nothing yet");
  const latencyEl = h("b", {}, "—");
  const latencySub = h("small", {}, "voice to voice");
  const stat = (ico, label, value, sub) =>
    h("div", { class: "stat" }, h("div", { class: "stat-i" }, icon(ico)), h("div", {}, h("span", { class: "stat-l" }, label), value, sub));
  const stats = h(
    "div",
    { class: "stats" },
    stat("clock", "Scammer's time wasted", clockEl, h("small", {}, "and counting")),
    stat("hash", "Details caught", detailsStat, detailsSub),
    stat("zap", "Reply speed (p50 / p90)", latencyEl, latencySub),
  );

  // ----- details panel -----
  const confirmedList = h("div", { class: "d-list" });
  const heardList = h("div", { class: "d-list" });
  const recordText = h("p", { class: "muted" });
  const recordRow = h(
    "div",
    { class: "decoy-row", hidden: true },
    h("h4", { class: "lane-h" }, icon("lock"), "Ramesh's bank records"),
    recordText,
    h("small", { class: "muted" }, "He never says these. A genuine bank has them on screen, so to play one, tell him the last four digits; a scammer usually cannot."),
  );
  const bankList = h("div", { class: "bank-list" });
  const bankRows = new Map(); // reportId -> row
  const bankSection = h(
    "div",
    { class: "decoy-row", hidden: true },
    h("h4", { class: "lane-h ok" }, icon("bank"), "Banks"),
    bankList,
    h("small", { class: "muted" }, "At 65% confidence or more a signed report goes to the bank automatically. Between 45% and 65% the detail is kept on a watchlist; if another call gives it again, the confidence goes up and the bank is told."),
  );
  const detailsEmpty = h("div", { class: "empty-note" }, icon("shield"), h("p", {}, "Nothing caught yet. Account numbers, UPI IDs, links and names show up here the moment the caller says them."));
  const confirmedHead = h("h4", { class: "lane-h ok", hidden: true }, icon("check"), "Confirmed by two checks");
  const heardHead = h("h4", { class: "lane-h", hidden: true }, icon("eye"), "Heard, waiting for a second check");
  const detailsCard = h(
    "section",
    { class: "card details-card" },
    h("div", { class: "card-h" }, icon("shield"), "Caught details"),
    detailsEmpty,
    confirmedHead,
    confirmedList,
    heardHead,
    heardList,
    bankSection,
    recordRow,
  );

  // ----- transcript panel -----
  const bubbles = h("div", { class: "bubbles", "aria-live": "polite" });
  const transcriptEmpty = h("div", { class: "empty-note" }, icon("chat"), h("p", {}, "The conversation appears here, word by word."));
  const transcriptCard = h("section", { class: "card transcript-card" }, h("div", { class: "card-h" }, icon("chat"), "Live transcript"), transcriptEmpty, bubbles);

  const banner = h("div", { class: "banner", hidden: true });
  const el = h(
    "div",
    { class: "dash" },
    banner,
    h("div", { class: "dash-top" }, gaugeCard, stageCard),
    stats,
    h("div", { class: "dash-cols" }, transcriptCard, detailsCard),
  );

  // ----- behaviour -----
  function setTone(tone) {
    lastTone = tone;
    gaugeCard.dataset.tone = tone;
  }

  function showBanner(text, tone = "info") {
    banner.hidden = !text;
    banner.className = `banner ${tone}`;
    banner.textContent = text || "";
  }

  function setClock(seconds) {
    clockEl.textContent = fmtClock(seconds);
  }

  function startClock(offsetSeconds = 0) {
    stopClock();
    clockStart = performance.now() - offsetSeconds * 1000;
    clockTimer = setInterval(() => setClock((performance.now() - clockStart) / 1000), 250);
  }

  function stopClock() {
    clearInterval(clockTimer);
    clockTimer = null;
  }

  function updateCounts() {
    const all = [...details.values()];
    const confirmed = all.filter((d) => d.data.confirmed).length;
    detailsStat.textContent = String(all.length);
    detailsSub.textContent = all.length ? `${confirmed} confirmed · ${all.length - confirmed} heard` : "nothing yet";
    detailsEmpty.hidden = all.length > 0;
    confirmedHead.hidden = confirmed === 0;
    heardHead.hidden = all.length - confirmed === 0;
  }

  function buildDetail(d) {
    const meta = DETAIL_META[d.type] || { label: humanize(d.type), icon: "hash" };
    const badge = h("span", { class: "badge" });
    const value = h("div", { class: "d-value" });
    const chips = h("div", { class: "chips" });
    const quote = h("div", { class: "d-quote" });
    const barFill = h("i");
    const pct = h("small", {});
    const node = h(
      "article",
      { class: "detail" },
      h("div", { class: "d-icon" }, icon(meta.icon)),
      h("div", { class: "d-main" }, h("div", { class: "d-type" }, meta.label, badge), value, chips, quote),
      h("div", { class: "d-conf" }, h("div", { class: "bar" }, barFill), pct),
    );
    node._parts = { badge, value, chips, quote, barFill, pct };
    return node;
  }

  function paintDetail(node, d) {
    const p = node._parts;
    p.badge.className = `badge ${d.confirmed ? "ok" : d.valid ? "warn" : "bad"}`;
    p.badge.textContent = d.confirmed ? "Confirmed" : d.valid ? "Heard" : "Looks invalid";
    p.value.textContent = d.normalizedValue || d.rawValue;
    p.value.classList.toggle("plain", ["person_name", "organisation_claimed", "app_name"].includes(d.type));
    clear(p.chips);
    for (const source of d.sources || []) p.chips.append(h("span", { class: "chip" }, SOURCE_LABELS[source] || humanize(source)));
    for (const flag of d.flags || []) p.chips.append(h("span", { class: "chip danger" }, flag === "apk" ? "APK file" : humanize(flag)));
    p.quote.textContent = d.evidence ? `“${d.evidence}”` : "";
    p.quote.hidden = !d.evidence;
    p.barFill.style.width = `${Math.round((d.confidence || 0) * 100)}%`;
    p.pct.textContent = `${Math.round((d.confidence || 0) * 100)}%`;
  }

  function onDetail(d, instant) {
    let entry = details.get(d.id);
    const isNew = !entry;
    if (isNew) {
      entry = { data: d, node: buildDetail(d) };
      details.set(d.id, entry);
      (d.confirmed ? confirmedList : heardList).prepend(entry.node);
      if (!instant) entry.node.classList.add("enter");
    }
    const wasConfirmed = entry.data.confirmed;
    entry.data = d;
    paintDetail(entry.node, d);
    if (!isNew && d.confirmed && !wasConfirmed) {
      if (instant) confirmedList.prepend(entry.node);
      else {
        flipMove(entry.node, confirmedList, confirmedList.firstChild);
        entry.node.classList.remove("pulse");
        void entry.node.offsetWidth;
        entry.node.classList.add("pulse");
      }
    }
    updateCounts();
  }

  function signalChip(item, tone) {
    const text = SIGNAL_LABELS[item.signal] || humanize(item.signal);
    const tip = [item.label, item.quote ? `Caller: “${item.quote}”` : ""].filter(Boolean).join("\n");
    return h("span", { class: `chip ${tone}`, title: tip }, text);
  }

  function onClassification(ev) {
    if (!ev.verdict) return onLegacyClassification(ev);
    const confidence = Math.max(0, Math.min(1, ev.confidence || 0));
    fill.setAttribute("stroke-dashoffset", String(CIRCUMFERENCE * (1 - confidence)));
    pctEl.textContent = ev.verdict === "undetermined" ? "—" : `${Math.round(confidence * 100)}%`;
    typeEl.textContent = verdictTitle(ev.verdict, ev.scamType);
    const who = ev.impersonatedEntity;
    if (ev.verdict === "scam") entityEl.textContent = who ? `Pretending to be: ${who}` : "Caller's claimed identity not clear yet.";
    else if (ev.verdict === "legitimate") entityEl.textContent = who ? `Genuine caller from: ${who}. No scam sign.` : "No scam sign. Looks like a genuine call.";
    else entityEl.textContent = who ? `Says they are from: ${who}. No clear scam sign yet.` : "No clear scam sign yet. Still listening.";
    setTone(ev.verdict === "scam" ? "danger" : ev.verdict === "legitimate" ? "safe" : "watch");
    clear(triggersEl);
    for (const flag of ev.redFlags || []) triggersEl.append(signalChip(flag, "danger"));
    for (const signal of ev.legitSignals || []) triggersEl.append(signalChip(signal, "ok"));
    if (ev.verdict === "scam") for (const phrase of (ev.triggerPhrases || []).slice(0, 2)) triggersEl.append(h("span", { class: "chip trigger" }, `“${phrase}”`));
    if (ev.stage) onStage(ev.stage);
  }

  // Recorded replays made before the verdict existed only carry a scam type.
  function onLegacyClassification(ev) {
    const confidence = Math.max(0, Math.min(1, ev.confidence || 0));
    fill.setAttribute("stroke-dashoffset", String(CIRCUMFERENCE * (1 - confidence)));
    pctEl.textContent = `${Math.round(confidence * 100)}%`;
    typeEl.textContent = scamLabel(ev.scamType);
    const harmless = ev.scamType === "not_scam";
    const unclear = !ev.scamType || ev.scamType === "undetermined";
    entityEl.textContent = ev.impersonatedEntity
      ? `Pretending to be: ${ev.impersonatedEntity}`
      : harmless ? "Sounds like an ordinary call."
      : unclear ? "Not enough said yet to judge this call."
      : "Caller's claimed identity not clear yet.";
    setTone(unclear ? "idle" : harmless ? "safe" : "danger");
    clear(triggersEl);
    for (const phrase of (ev.triggerPhrases || []).slice(0, 4)) triggersEl.append(h("span", { class: "chip trigger" }, `“${phrase}”`));
    if (ev.stage) onStage(ev.stage);
  }

  function onBankReport(ev) {
    let row = bankRows.get(ev.key);
    if (!row) {
      row = h("a", { class: "bank-row" });
      bankRows.set(ev.key, row);
      bankList.append(row);
    }
    const meta = DETAIL_META[ev.detailType] || { label: humanize(ev.detailType), icon: "hash" };
    const state = bankItemState(ev);
    const watching = ev.stage !== "reported";
    row.href = ev.bankCode && !watching ? `#/banks/${ev.bankCode}` : "#/banks";
    row.classList.toggle("watch", watching);
    const where = ev.bankName ? `${ev.bankName} · ${ROUTED_BY_LABELS[ev.routedBy] || ev.routedBy}` : "bank not known yet";
    row.replaceChildren(
      h("span", { class: "bank-i" }, icon(watching ? "eye" : "bank")),
      h("div", { class: "bank-main" }, h("b", {}, `${meta.label} ${ev.value}`), h("small", { class: "muted" }, watching ? `${where} · needs 65% to report` : where)),
      h("span", { class: `chip ${watching ? "" : "ok"}`, title: "Confidence: this call and any earlier call that gave it" }, pct(ev.confidence)),
      ev.sightings > 1 ? h("span", { class: "chip danger" }, `${ev.sightings} calls`) : null,
      h("span", { class: `badge ${state.tone}` }, state.label),
    );
    row.title = ev.reason || "";
    bankSection.hidden = false;
  }

  function onRecord(ev) {
    const last4 = ev.last4 || {};
    recordText.textContent = `${ev.bank}, ${ev.branch} branch · account ends ${last4.account} · Aadhaar ends ${last4.aadhaar} · debit card ends ${last4.card} · UPI on ${ev.upiApp}`;
    recordRow.hidden = false;
  }

  function onStage(stage) {
    const index = STAGES.findIndex((s) => s.id === stage);
    if (index < 0) return;
    stageNodes.forEach((node, i) => {
      node.classList.toggle("done", i < index);
      node.classList.toggle("active", i === index);
    });
  }

  function onTranscript(ev) {
    const speaker = ev.speaker === "caller" ? "caller" : "persona";
    const nearBottom = bubbles.scrollHeight - bubbles.scrollTop - bubbles.clientHeight < 90;
    let bubble = liveBubbles[speaker];
    if (!bubble) {
      bubble = h(
        "div",
        { class: `bubble ${speaker}` },
        h("div", { class: "b-who" }, speaker === "caller" ? callerLabel : personaLabel, h("time", {})),
        h("p", { class: "b-text" }),
      );
      bubbles.append(bubble);
      transcriptEmpty.hidden = true;
      if (!ev.final) liveBubbles[speaker] = bubble;
    }
    bubble.querySelector(".b-text").textContent = ev.translating && !ev.final ? "Translating to English…" : ev.text;
    bubble.classList.toggle("partial", !ev.final);
    bubble.classList.toggle("translating", Boolean(ev.translating) && !ev.final);
    if (ev.final) {
      delete liveBubbles[speaker];
      if (ev.tSec != null) bubble.querySelector("time").textContent = ` · ${fmtClock(ev.tSec)}`;
    }
    if (nearBottom) bubbles.scrollTop = bubbles.scrollHeight;
  }

  function settleLive() {
    for (const [speaker, bubble] of Object.entries(liveBubbles)) {
      const text = bubble.querySelector(".b-text").textContent.trim();
      const duplicate = [...bubbles.querySelectorAll(`.bubble.${speaker}:not(.partial)`)].some((other) => other !== bubble && other.querySelector(".b-text").textContent.includes(text.slice(0, 60)));
      if (duplicate) bubble.remove();
      else bubble.classList.remove("partial");
      delete liveBubbles[speaker];
    }
  }

  function handle(ev, { instant = false } = {}) {
    if (instant) el.classList.add("no-anim");
    switch (ev.type) {
      case "transcript":
        onTranscript(ev);
        break;
      case "detail":
        onDetail(ev.detail, instant);
        break;
      case "classification":
        onClassification(ev);
        break;
      case "stage":
        onStage(ev.stage);
        break;
      case "record":
        onRecord(ev);
        break;
      case "bank_report":
        onBankReport(ev);
        break;
      case "latency":
        latencyEl.textContent = `${ev.p50 ?? ev.ms} / ${ev.p90 ?? ev.ms} ms`;
        latencySub.textContent = `last reply ${ev.ms} ms`;
        break;
      case "time_limit":
        showBanner("Time limit reached. The call is wrapping up.", "warn");
        break;
      case "ended":
        settleLive();
        stopClock();
        if (ev.durationSec != null) setClock(ev.durationSec);
        if (ev.verdict === "legitimate") showBanner("Call ended. It looked genuine, so no strain card was made.", "ok");
        else if (ev.verdict === "undetermined") showBanner("Call ended without a clear scam sign, so no strain card was made.", "info");
        else showBanner("Call ended. Evidence and strain card are ready.", "ok");
        break;
      case "error":
        showBanner(ev.message || "Something went wrong.", "error");
        break;
      default:
        break;
    }
    if (instant) requestAnimationFrame(() => el.classList.remove("no-anim"));
  }

  function reset() {
    stopClock();
    details.clear();
    for (const key of Object.keys(liveBubbles)) delete liveBubbles[key];
    clear(confirmedList);
    clear(heardList);
    clear(bubbles);
    transcriptEmpty.hidden = false;
    updateCounts();
    fill.setAttribute("stroke-dashoffset", String(CIRCUMFERENCE));
    pctEl.textContent = "0%";
    typeEl.textContent = "Listening…";
    entityEl.textContent = "Waiting for the caller to say something.";
    clear(triggersEl);
    recordText.textContent = "";
    recordRow.hidden = true;
    bankRows.clear();
    clear(bankList);
    bankSection.hidden = true;
    setTone("idle");
    stageNodes.forEach((node) => node.classList.remove("done", "active"));
    latencyEl.textContent = "—";
    latencySub.textContent = "voice to voice";
    setClock(0);
    showBanner("");
  }

  reset();
  return { el, handle, reset, startClock, stopClock, setClock, showBanner, get tone() { return lastTone; } };
}
