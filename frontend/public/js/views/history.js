import { api } from "../api.js";
import { emptyState, errorState, pageHeader, skeletons } from "../components.js";
import { fmtDate, fmtDuration, h, icon, observeReveal, scamLabel, verdictTitle } from "../util.js";

export function HistoryView() {
  const el = h("div", { class: "page" }, pageHeader("History", "Every call from this browser. Recordings are kept privately for 14 days."), skeletons(3));

  async function load() {
    let calls;
    try {
      ({ calls } = await api.calls());
    } catch (err) {
      el.replaceChildren(pageHeader("History"), errorState(err.message, load));
      return;
    }
    if (!calls.length) {
      el.replaceChildren(
        pageHeader("History", "Every call from this browser. Recordings are kept privately for 14 days."),
        emptyState({ iconName: "clock", title: "No calls yet", text: "Calls and text chats you take will show up here, with the recording, transcript and evidence pack." }),
      );
      observeReveal(el);
      return;
    }
    const cards = calls.map((call) => {
      const counts = call.counts || {};
      const live = call.status === "live";
      return h(
        "a",
        { class: "card call-card reveal", href: `#/call/${call.callId}` },
        h(
          "div",
          { class: "cc-top" },
          h("span", { class: "cc-icon" }, icon(call.mode === "text" ? "chat" : "phone")),
          h("div", {}, h("h3", {}, call.scamType ? scamLabel(call.scamType) : live ? "In progress or unfinished" : call.verdict ? verdictTitle(call.verdict) : "Unclassified"), h("small", { class: "muted" }, fmtDate(call.startedAt))),
          h("span", { class: "grow" }),
          call.recording ? h("span", { class: "chip ok" }, icon("volume"), "Recording") : null,
        ),
        call.impersonatedEntity ? h("p", { class: "muted" }, call.verdict && call.verdict !== "scam" ? "Says they are from " : "Pretending to be ", h("b", {}, call.impersonatedEntity)) : null,
        h(
          "div",
          { class: "cc-metrics" },
          h("span", {}, icon("clock"), call.durationSec != null ? fmtDuration(call.durationSec) : "—"),
          h("span", {}, icon("shield"), `${counts.confirmed ?? 0} confirmed · ${counts.details ?? 0} details`),
          h("span", {}, icon("chat"), `${counts.turns ?? 0} turns`),
        ),
      );
    });
    el.replaceChildren(pageHeader("History", `${calls.length} call${calls.length === 1 ? "" : "s"} from this browser. Recordings are kept privately for 14 days.`), h("div", { class: "grid cards" }, cards));
    observeReveal(el);
  }
  load();
  return { el };
}
