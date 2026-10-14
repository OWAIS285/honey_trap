// Reusable UI pieces: page headers, empty states, skeletons, strain cards.

import { h, icon, scamLabel } from "./util.js";

export function pageHeader(title, subtitle, ...actions) {
  return h(
    "header",
    { class: "page-h reveal" },
    h("div", {}, h("h1", {}, title), subtitle && h("p", { class: "muted" }, subtitle)),
    actions.length ? h("div", { class: "page-actions" }, actions) : null,
  );
}

export function emptyState({ iconName = "shield", title, text, action }) {
  return h("div", { class: "empty card reveal" }, h("div", { class: "empty-i" }, icon(iconName)), h("h3", {}, title), h("p", { class: "muted" }, text), action || null);
}

export function skeletons(count = 3) {
  return h("div", { class: "grid skeleton-grid" }, Array.from({ length: count }, () => h("div", { class: "card skeleton" }, h("i"), h("i"), h("i"))));
}

export function errorState(message, retry) {
  return h(
    "div",
    { class: "empty card" },
    h("div", { class: "empty-i bad" }, icon("alert")),
    h("h3", {}, "Something went wrong"),
    h("p", { class: "muted" }, message),
    retry ? h("button", { class: "btn primary", type: "button", onClick: retry }, "Try again") : null,
  );
}

/** A redacted scam-script card ("strain"). */
export function strainCard(strain, { onDrill, compact = false } = {}) {
  const card = h(
    "article",
    { class: `card strain ${compact ? "compact" : ""} reveal` },
    h(
      "div",
      { class: "strain-top" },
      h("span", { class: "strain-icon" }, icon("virus")),
      h("div", {}, h("div", { class: "eyebrow" }, strain.demo ? "Example strain" : "Strain captured"), h("h3", {}, scamLabel(strain.scamType))),
      h("span", { class: "grow" }),
      strain.language ? h("span", { class: "chip" }, icon("globe"), strain.language) : null,
    ),
    strain.impersonatedEntity ? h("p", { class: "muted" }, "Pretends to be: ", h("b", {}, strain.impersonatedEntity)) : null,
    h("ol", { class: "timeline" }, (strain.steps || []).map((step, i) => h("li", {}, h("span", { class: "tl-dot" }, String(i + 1)), h("p", {}, step)))),
  );
  if (!compact) {
    if (strain.paymentMethod) card.append(h("div", { class: "strain-pay" }, icon("rupee"), h("div", {}, h("small", {}, "How they want the money"), h("p", {}, strain.paymentMethod))));
    if (strain.scriptExcerpts?.length) {
      card.append(h("div", { class: "quotes" }, strain.scriptExcerpts.map((q) => h("blockquote", {}, q))));
    }
    if (strain.redFlags?.length) {
      card.append(
        h("div", { class: "flags" }, h("h4", {}, icon("shield"), "Warning signs to teach"), h("ul", {}, strain.redFlags.map((flag) => h("li", {}, flag)))),
      );
    }
  }
  if (onDrill) {
    card.append(h("button", { class: "btn primary", type: "button", onClick: onDrill }, icon("users"), "Create a family drill"));
  }
  return card;
}

export function chip(text, extra = "") {
  return h("span", { class: `chip ${extra}` }, text);
}
