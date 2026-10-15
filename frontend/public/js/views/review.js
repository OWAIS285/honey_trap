// Call review: recording with click-to-seek transcript, evidence pack (JSON / print to PDF) and the captured strain.

import { api } from "../api.js";
import { BRAND } from "../brand.js";
import { backLink, errorState, pageHeader, skeletons, strainCard } from "../components.js";
import { createAudioPlayer } from "../player.js";
import { DETAIL_META, SOURCE_LABELS, downloadBlob, fmtClock, fmtDate, fmtDuration, h, humanize, icon, observeReveal, scamLabel, toast } from "../util.js";

export const DISCLAIMER =
  "Details were stated by an unverified caller during an automated decoy call and may be mis-heard or belong to an innocent third party. This pack is a lead for investigators, not a finding that any account is fraudulent.";

export function ReviewView({ id }) {
  const back = backLink("#/history", "History");
  const el = h("div", { class: "page review" }, back, pageHeader("Call review", "Loading…"), skeletons(2));
  let player = null;
  let destroyed = false;

  load();

  async function load() {
    let data;
    try {
      data = await api.call(id);
    } catch (err) {
      el.replaceChildren(back, pageHeader("Call review"), errorState(err.status === 404 ? "This call was not found in this browser's history. It may be older than 14 days." : err.message, err.status === 404 ? null : load));
      return;
    }
    if (destroyed) return;
    render(data);
  }

  function render({ call, turns, details, strain, recordingUrl }) {
    const confirmed = details.filter((d) => d.confirmed);
    const unconfirmed = details.filter((d) => !d.confirmed);
    const seekers = [];
    const seekTo = (seconds) => {
      if (!player) return toast("No recording for this call.", "error");
      player.seek(Math.max(0, seconds));
      player.play().catch(() => {});
    };

    const actions = [
      h("button", { class: "btn", type: "button", onClick: downloadEvidence }, icon("download"), "Evidence (JSON)"),
      h("button", { class: "btn", type: "button", onClick: () => window.print() }, icon("printer"), "Print / save as PDF"),
      recordingUrl ? h("a", { class: "btn", href: api.recordingDownloadUrl(recordingUrl), download: `call-${call.callId}.wav` }, icon("download"), "Recording (WAV)") : null,
      call.strainId ? h("a", { class: "btn primary", href: `#/drill/new/${call.strainId}` }, icon("users"), "Create family drill") : null,
    ];

    const tile = (label, value, sub) => h("div", { class: "tile" }, h("span", {}, label), h("b", {}, value), sub ? h("small", {}, sub) : null);
    const tiles = h(
      "div",
      { class: "tiles" },
      tile("Scam type", scamLabel(call.scamType), call.scamTypeConfidence ? `${Math.round(call.scamTypeConfidence * 100)}% confidence` : ""),
      tile("Pretending to be", call.impersonatedEntity || "Unclear"),
      tile("Time wasted", call.durationSec != null ? fmtDuration(call.durationSec) : "—"),
      tile("Details", `${confirmed.length} confirmed`, `${unconfirmed.length} heard, not confirmed`),
      tile("Reply speed", call.latencyMsP50 ? `${Math.round(call.latencyMsP50)} ms` : "—", call.latencyMsP90 ? `p90 ${Math.round(call.latencyMsP90)} ms` : "p50"),
    );

    // transcript
    const lines = turns.map((turn, i) => {
      const start = i > 0 ? turns[i - 1].tSec || 0 : 0;
      const row = h(
        "button",
        { class: `line ${turn.speaker}`, type: "button", onClick: () => seekTo(start - 0.4), "aria-label": `Play from ${fmtClock(start)}` },
        h("span", { class: "who" }, turn.speaker === "caller" ? "Caller" : "Ramesh", h("time", {}, ` · ${fmtClock(turn.tSec || 0)}`)),
        h("span", { class: "txt" }, turn.textEn || turn.text),
      );
      seekers.push({ row, start, end: turn.tSec || start + 1 });
      return row;
    });
    const transcript = h("section", { class: "card transcript-card review-transcript" }, h("div", { class: "card-h" }, icon("chat"), "Transcript", recordingUrl ? h("small", {}, "click a line to hear it") : null), h("div", { class: "lines" }, lines));

    // evidence
    const row = (d) => {
      const meta = DETAIL_META[d.type] || { label: humanize(d.type), icon: "hash" };
      const at = d.firstSeenSec;
      const plain = ["person_name", "organisation_claimed", "app_name"].includes(d.type);
      return h(
        "article",
        { class: "ev-row" },
        h(
          "div",
          { class: "ev-head" },
          h("span", { class: "ev-type" }, icon(meta.icon), meta.label),
          h("span", { class: `badge ${d.confirmed ? "ok" : d.valid ? "warn" : "bad"}` }, d.confirmed ? "Confirmed" : d.valid ? "Heard" : "Looks invalid"),
          h("span", { class: "grow" }),
          h("span", { class: "ev-conf" }, `${Math.round((d.confidence || 0) * 100)}% confidence`),
        ),
        h("div", { class: `ev-value ${plain ? "" : "mono"}` }, d.normalizedValue || d.rawValue),
        h(
          "div",
          { class: "chips" },
          (d.sources || []).map((s) => h("span", { class: "chip" }, SOURCE_LABELS[s] || humanize(s))),
          (d.flags || []).map((f) => h("span", { class: "chip danger" }, f === "apk" ? "APK file" : humanize(f))),
          at != null ? h("button", { class: "chip action", type: "button", onClick: () => seekTo(at - 3) }, icon("play"), `heard at ${fmtClock(at)}`) : null,
        ),
        d.evidence ? h("div", { class: "ev-quote" }, `“${d.evidence}”`) : null,
      );
    };
    const table = (items) => h("div", { class: "ev-list" }, items.map(row));
    const evidence = h(
      "section",
      { class: "card evidence" },
      h("div", { class: "card-h" }, icon("shield"), "Evidence pack"),
      h("div", { class: "disclaimer" }, icon("alert"), h("p", {}, DISCLAIMER)),
      confirmed.length ? h("div", {}, h("h4", { class: "lane-h ok" }, icon("check"), `Confirmed (${confirmed.length})`), table(confirmed)) : h("p", { class: "muted" }, "No detail was confirmed by two checks in this call."),
      unconfirmed.length ? h("div", {}, h("h4", { class: "lane-h" }, icon("eye"), `Heard, not confirmed (${unconfirmed.length})`), table(unconfirmed)) : null,
    );

    const printHead = h(
      "div",
      { class: "print-only" },
      h("h1", {}, `${BRAND.name}: evidence pack`),
      h("p", {}, `Call ${call.callId} · ${fmtDate(call.startedAt)} · ${call.mode === "text" ? "text chat" : "voice call"} · ${call.durationSec != null ? fmtDuration(call.durationSec) : ""}`),
    );

    const playerSlot = h("div", { class: "slot no-print" });
    el.replaceChildren(
      printHead,
      back,
      pageHeader(scamLabel(call.scamType), `${fmtDate(call.startedAt)} · ${call.mode === "text" ? "text chat" : "voice call"}`, ...actions),
      tiles,
      playerSlot,
      h("div", { class: "review-cols" }, transcript, evidence),
    );
    if (strain) el.append(h("div", { class: "section-gap" }, strainCard(strain, { onDrill: strain.strainId ? () => (location.hash = `#/drill/new/${strain.strainId}`) : null })));
    observeReveal(el);

    if (recordingUrl) {
      playerSlot.append(h("div", { class: "card loading-card" }, h("span", { class: "spinner" }), h("p", { class: "muted" }, "Loading the recording…")));
      api
        .recordingBlob(recordingUrl)
        .then((blob) => {
          if (destroyed) return;
          player = createAudioPlayer({
            blob,
            callerLabel: "Caller",
            personaLabel: "Ramesh",
            onFrame: (t) => {
              let current = null;
              for (const s of seekers) if (t >= s.start && t < s.end) current = s;
              for (const s of seekers) s.row.classList.toggle("active", s === current);
              if (current && !player.audio.paused) current.row.scrollIntoView({ block: "nearest", behavior: "smooth" });
            },
          });
          playerSlot.replaceChildren(player.el);
        })
        .catch(() => playerSlot.replaceChildren(h("div", { class: "inline-error" }, icon("alert"), h("span", {}, "The recording could not be loaded."))));
    } else {
      playerSlot.append(h("div", { class: "card note-card" }, icon("chat"), h("p", { class: "muted" }, call.mode === "text" ? "This was a text chat, so there is no audio recording." : "No recording was saved for this call.")));
    }

    async function downloadEvidence() {
      try {
        downloadBlob(await api.evidenceBlob(call.callId), `evidence-${call.callId}.json`);
      } catch (err) {
        toast(err.message, "error");
      }
    }
  }

  return {
    el,
    destroy() {
      destroyed = true;
      player?.destroy();
    },
  };
}
