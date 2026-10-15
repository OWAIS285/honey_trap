// Replay: a recorded call (audio + timed events) played back through the same dashboard. Needs no microphone and no backend.

import { errorState, strainCard } from "../components.js";
import { createDashboard } from "../dashboard.js";
import { createAudioPlayer } from "../player.js";
import { setEnergy } from "../fx.js";
import { DETAIL_META, fmtClock, h, icon, scamLabel } from "../util.js";

const REPLAYS = {
  en: { url: "replay/replay-en.json", label: "English" },
  hi: { url: "replay/replay-hi.json", label: "हिन्दी · Hinglish" },
};

export function ReplayView({ lang } = {}) {
  const which = REPLAYS[lang] ? lang : "en";
  const dash = createDashboard({ callerLabel: "Scammer (AI actor)", personaLabel: "Ramesh (AI decoy)" });
  const strainSlot = h("div", { class: "slot" });
  const left = h("div", { class: "call-left" });
  const el = h("div", { class: "call-page replay", "data-state": "idle" }, left, dash.el);
  let player = null;
  let destroyed = false;

  const body = h("section", { class: "card phone replay-card" }, h("div", { class: "loading" }, h("span", { class: "spinner" }), h("p", { class: "muted" }, "Loading the replay…")));
  left.append(body, strainSlot);

  load();

  async function load() {
    let data;
    try {
      const response = await fetch(REPLAYS[which].url, { cache: "no-cache" });
      if (!response.ok) throw new Error("missing");
      data = await response.json();
    } catch {
      body.replaceWith(errorState("The replay is still being prepared. Try the live call or the text chat in the meantime."));
      return;
    }
    let blob = null;
    if (data.audio) {
      try {
        const response = await fetch(data.audio);
        if (!response.ok) throw new Error("audio");
        blob = await response.blob();
      } catch {
        blob = null;
      }
    }
    if (destroyed) return;
    mount(data, blob);
  }

  function mount(data, blob) {
    const events = (data.events || []).filter((e) => e.type !== "ready").sort((a, b) => a.t - b.t);
    let index = 0;
    let lastT = 0;

    const apply = (event, instant) => {
      dash.handle(event, { instant });
      if (event.type === "ended" && event.strain) {
        strainSlot.replaceChildren(strainCard({ ...event.strain, strainId: event.strainId }));
      }
    };

    const advance = (t) => {
      if (t + 0.05 < lastT || t - lastT > 1.5) {
        dash.reset();
        strainSlot.replaceChildren();
        index = 0;
        while (index < events.length && events[index].t <= t) apply(events[index++], true);
      } else {
        while (index < events.length && events[index].t <= t) apply(events[index++], false);
      }
      lastT = t;
      dash.setClock(t);
      setEnergy(player && !player.audio.paused ? 0.55 : 0);
    };

    const highlights = [];
    const seen = new Set();
    const finalType = events.find((e) => e.type === "ended")?.scamType || [...events].reverse().find((e) => e.type === "classification")?.scamType;
    for (const event of events) {
      if (event.type === "classification" && !seen.has("class") && event.scamType === finalType) {
        seen.add("class");
        highlights.push({ t: event.t, label: `Scam type spotted: ${scamLabel(event.scamType)}`, icon: "alert" });
      } else if (event.type === "detail" && event.detail.confirmed && !seen.has(event.detail.id)) {
        seen.add(event.detail.id);
        const meta = DETAIL_META[event.detail.type] || { label: event.detail.type, icon: "hash" };
        highlights.push({ t: event.t, label: `${meta.label} confirmed`, icon: meta.icon });
      }
    }

    highlights.sort((a, b) => a.t - b.t);
    const head = h(
      "div",
      { class: "replay-head" },
      h("span", { class: "tag" }, "Recorded demo"),
      h("h2", {}, data.title || "Digital-arrest call, recorded"),
      h("p", { class: "muted" }, data.description || "A fictional AI scammer phones the decoy. Ramesh answers live. Everything on the right was produced by the real pipeline while this call happened."),
    );
    const chips = h(
      "div",
      { class: "highlights" },
      highlights.slice(0, 5).map((item) =>
        h("button", { class: "chip action", type: "button", onClick: () => (player?.seek(Math.max(0, item.t - 1)), player?.play()) }, icon(item.icon), `${fmtClock(item.t)} · ${item.label}`),
      ),
    );

    if (!blob) {
      body.replaceChildren(head, h("p", { class: "inline-error" }, icon("alert"), h("span", {}, "The audio for this replay is missing, so only the transcript can be shown.")));
      events.forEach((event) => apply(event, true));
      return;
    }

    const finish = () => {
      while (index < events.length) apply(events[index++], false);
    };
    player = createAudioPlayer({ blob, callerLabel: "Scammer", personaLabel: "Ramesh", onFrame: advance, onEnded: finish });
    body.replaceChildren(
      head,
      h("button", { class: "btn primary lg block", type: "button", onClick: () => player.play().catch(() => {}) }, icon("play"), "Play the replay"),
      highlights.length ? h("div", {}, h("small", { class: "muted" }, "Jump to a key moment"), chips) : null,
    );
    left.insertBefore(player.el, strainSlot);
    advance(0);
  }

  return {
    el: h(
      "div",
      { class: "replay-wrap" },
      h(
        "div",
        { class: "seg replay-langs", role: "tablist", "aria-label": "Replay language" },
        Object.entries(REPLAYS).map(([id, item]) =>
          h("a", { class: `seg-item ${id === which ? "active" : ""}`, href: id === "en" ? "#/replay" : `#/replay/${id}`, role: "tab", "aria-selected": String(id === which), lang: id === "hi" ? "hi" : "en" }, icon("globe"), item.label),
        ),
      ),
      el,
    ),
    destroy() {
      destroyed = true;
      setEnergy(0);
      player?.destroy();
    },
  };
}
