// The product name lives here. Change `name` (and the tagline) to rename the product everywhere in the interface.

import { h } from "./util.js";

export const BRAND = {
  name: "Stallwart",
  tagline: "The AI decoy that wastes scammers' time",
  introLine: "Pick up. Stall. Catch them.",
};

/** Name in the accent colour; a two-word name keeps its first word plain, e.g. "Scam" + "Shield". */
export function brandText() {
  const words = BRAND.name.split(" ");
  const last = words.pop();
  return h("span", {}, words.join(" "), h("em", {}, last));
}

export const pageTitle = (page) => (page ? `${page} · ${BRAND.name}` : `${BRAND.name}: ${BRAND.tagline}`);
