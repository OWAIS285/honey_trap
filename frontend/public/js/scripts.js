// Sample scammer scripts (fictional) that a tester reads aloud or sends as text during the demo call.

import { copyText, h, icon } from "./util.js";

export const SCRIPTS = {
  english: {
    label: "English",
    lines: [
      "Hello sir, I am calling from the CBI cyber crime department. A parcel in your name was caught with illegal items.",
      "There is an arrest warrant. Do not tell anyone. To clear your name you must transfer 50,000 rupees right now.",
      "The UPI ID is rahul dot sharma at okaxis. Please confirm the ID back to me.",
      "Yes that is correct. If you cannot use UPI, the bank account is one two three four five six seven eight nine zero one two, IFSC S B I N zero zero zero one two three four.",
    ],
  },
  hinglish: {
    label: "Hinglish",
    lines: [
      "Hello uncle, main CBI officer bol raha hoon. Aapke Aadhaar se ek parcel pakda gaya hai.",
      "Arrest warrant ready hai. Kisi ko mat batana. Abhi pachaas hazaar rupaye bhejne honge.",
      "UPI ID hai rahul dot sharma at okaxis. Dobara bataiye jo maine bola.",
      "Haan sahi hai. Account number hai nau aath saat chhe paanch char teen do ek shunya, IFSC SBIN0001234.",
    ],
  },
  hindi: {
    label: "हिन्दी",
    lines: [
      "नमस्ते अंकल, मैं सीबीआई साइबर क्राइम से बोल रहा हूँ। आपके आधार से एक पार्सल पकड़ा गया है।",
      "आपके नाम गिरफ़्तारी वारंट निकल चुका है। किसी को मत बताइए। अभी पचास हज़ार रुपये भेजने होंगे।",
      "यूपीआई आईडी है राहुल डॉट शर्मा एट ओके एक्सिस। दोबारा बोलकर बताइए।",
      "हाँ सही है। खाता नंबर है एक दो तीन चार पाँच छह सात आठ नौ शून्य एक दो, आईएफ़एससी एस बी आई एन शून्य शून्य शून्य एक दो तीन चार।",
    ],
  },
};

/** Tabbed script card. onSend(text) is optional; without it the lines can only be copied. */
export function scriptPanel({ onSend, title = "Play the scammer" } = {}) {
  let active = "english";
  const tabs = h("div", { class: "tabs", role: "tablist" });
  const list = h("ol", { class: "script-list" });

  function paint() {
    tabs.replaceChildren(
      ...Object.entries(SCRIPTS).map(([key, value]) =>
        h("button", { class: `tab ${key === active ? "active" : ""}`, type: "button", role: "tab", "aria-selected": String(key === active), onClick: () => ((active = key), paint()) }, value.label),
      ),
    );
    list.replaceChildren(
      ...SCRIPTS[active].lines.map((line, i) =>
        h(
          "li",
          { class: "script-line" },
          h("span", { class: "n" }, String(i + 1)),
          h("p", { lang: active === "hindi" ? "hi" : "en" }, line),
          h(
            "span",
            { class: "script-actions" },
            onSend && h("button", { class: "btn mini primary", type: "button", onClick: () => onSend(line), "aria-label": `Send line ${i + 1}` }, icon("send"), "Send"),
            h("button", { class: "btn mini ghost", type: "button", onClick: () => copyText(line), "aria-label": `Copy line ${i + 1}` }, icon("copy")),
          ),
        ),
      ),
    );
  }
  paint();
  return h(
    "section",
    { class: "card script-card" },
    h("div", { class: "card-h" }, icon("file"), title),
    h("p", { class: "muted small" }, "Read these lines aloud into the microphone, or press Send to type them in. Every name, number and ID here is fictional."),
    tabs,
    list,
  );
}
