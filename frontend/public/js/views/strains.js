import { api } from "../api.js";
import { emptyState, errorState, pageHeader, skeletons, strainCard } from "../components.js";
import { h, icon, observeReveal } from "../util.js";

export function StrainsView() {
  const el = h("div", { class: "page" }, pageHeader("Strain library", "Each captured call becomes a redacted card of how the scam works."), skeletons(2));

  async function load() {
    let strains;
    try {
      ({ strains } = await api.strains());
    } catch (err) {
      el.replaceChildren(pageHeader("Strain library"), errorState(err.message, load));
      return;
    }
    const mine = strains.filter((s) => !s.demo);
    const demo = strains.filter((s) => s.demo);
    const open = (strain) => () => (location.hash = `#/drill/new/${strain.strainId}`);
    el.replaceChildren(
      pageHeader("Strain library", "Each captured call becomes a redacted card of how the scam works. No names, numbers or UPI IDs survive in it.", h("a", { class: "btn primary", href: "#/call" }, icon("phone"), "Capture a new one")),
      mine.length
        ? h("div", { class: "grid cards" }, mine.map((s) => strainCard(s, { onDrill: open(s) })))
        : emptyState({ iconName: "virus", title: "No strains captured yet", text: "Finish a call and its strain card appears here. Until then, try the example below.", action: h("a", { class: "btn primary", href: "#/call" }, icon("phone"), "Take a live call") }),
      demo.length ? h("div", { class: "section-gap" }, h("h2", { class: "sub-h reveal" }, "Example strain"), h("div", { class: "grid cards" }, demo.map((s) => strainCard(s, { onDrill: open(s) })))) : null,
    );
    observeReveal(el);
  }
  load();
  return { el };
}
