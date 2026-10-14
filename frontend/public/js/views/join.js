// Parent-facing page: opened from a WhatsApp link. Big, simple, bilingual, consent-first practice call.

import { api } from "../api.js";
import { Visualizer } from "../audio.js";
import { errorState } from "../components.js";
import { CallSession } from "../session.js";
import { fmtClock, h, icon, toast } from "../util.js";

export function JoinView({ id, key }) {
  const el = h("div", { class: "join" }, h("div", { class: "loading" }, h("span", { class: "spinner" })));
  let session = null;
  let raf = 0;
  let viz = null;

  api
    .invite(id, key)
    .then((invite) => showIncoming(invite))
    .catch((err) => el.replaceChildren(errorState(err.status === 404 ? "This invitation link is not valid or has expired. Please ask your family member for a new one." : err.message)));

  function showIncoming(invite) {
    el.replaceChildren(
      h(
        "section",
        { class: "incoming" },
        h("div", { class: "ring-wrap" }, h("span", { class: "ring r1" }), h("span", { class: "ring r2" }), h("span", { class: "ring r3" }), h("div", { class: "phone-badge" }, icon("phone"))),
        h("p", { class: "eyebrow center" }, "Incoming practice call · अभ्यास कॉल"),
        h("h1", {}, `Namaste ${invite.parentName}`),
        h("p", { class: "lead" }, `${invite.familyName} has set up a short practice call, so you can see how scammers talk and how to stay safe.`),
        h("p", { class: "lead hi", lang: "hi" }, `${invite.familyName} ने आपके लिए एक छोटी अभ्यास कॉल रखी है। इससे आप पहचान पाएँगे कि ठग कैसे बात करते हैं।`),
        h("ul", { class: "safe-list" }, [
          "It is only practice. Nothing real will happen.",
          "Please do not say any real bank, OTP, Aadhaar or card numbers.",
          "You can hang up at any time.",
        ].map((t) => h("li", {}, icon("shield"), t))),
        h("button", { class: "btn primary xl block", type: "button", onClick: () => startCall(invite) }, icon("phone"), "Pick up · फ़ोन उठाइए"),
        h("p", { class: "fineprint center" }, `The call lasts up to ${Math.round(invite.maxSeconds / 60)} minutes and uses your microphone.`),
      ),
    );
  }

  async function startCall(invite) {
    const captions = h("p", { class: "caption", "aria-live": "polite" }, "…");
    const stepLabel = h("span", {}, "Practice call connected");
    const dots = h("div", { class: "step-dots" });
    const timer = h("span", { class: "call-timer" }, "00:00");
    const orb = h("div", { class: "orb-wrap big", "data-state": "connecting" }, h("span", { class: "ring r1" }), h("span", { class: "ring r2" }), h("span", { class: "ring r3" }), h("div", { class: "avatar" }, h("span", {}, "?")));
    const canvas = h("canvas", { class: "viz", "aria-hidden": "true" });
    const hang = h("button", { class: "btn danger xl round", type: "button", "aria-label": "Hang up", onClick: () => session?.end() }, icon("hangup"));
    const coachTag = h("div", { class: "coach-tag", hidden: true }, icon("heart"), "Your coach is speaking");
    const input = h("input", { class: "input", type: "text", maxlength: "300", placeholder: "Or type your reply here", "aria-label": "Type your reply" });
    const typeRow = h("form", { class: "type-row", onSubmit: (e) => (e.preventDefault(), input.value.trim() && (session?.sendText(input.value.trim()), (input.value = ""))) }, input, h("button", { class: "btn primary round sm", type: "submit", "aria-label": "Send" }, icon("send")));

    let level = 0;
    let seconds = 0;
    let clock = null;
    const callScreen = h("section", { class: "incall" }, h("div", { class: "incall-top" }, stepLabel, timer), orb, h("h2", {}, "Practice call"), h("p", { class: "muted" }, "Speak normally, as you would on a real call."), canvas, coachTag, captions, dots, h("div", { class: "controls" }, hang), typeRow);
    el.replaceChildren(callScreen);
    viz = new Visualizer(canvas, { frequency: () => session?.frequency() || null, micLevel: () => session?.micLevel() || 0 });
    viz.start();
    const frame = () => {
      level += ((session ? Math.max(session.personaLevel(), session.micLevel() * 0.8) : 0) - level) * 0.3;
      orb.style.setProperty("--level", level.toFixed(3));
      raf = requestAnimationFrame(frame);
    };
    frame();

    session = new CallSession({
      path: "/ws/drill",
      start: { drillId: id, key },
      voice: true,
      onState: (s) => {
        if (s === "ending") captions.textContent = "Finishing up…";
      },
      onEvent: (ev) => {
        switch (ev.type) {
          case "persona_audio":
            orb.dataset.state = ev.playing ? "speaking" : "listening";
            break;
          case "ready":
            orb.dataset.state = "listening";
            clock = setInterval(() => (timer.textContent = fmtClock(++seconds)), 1000);
            dots.replaceChildren(...Array.from({ length: ev.steps || 0 }, () => h("i", {})));
            break;
          case "transcript":
            if (ev.speaker !== "you") captions.textContent = ev.text;
            break;
          case "step":
            stepLabel.textContent = `Step ${ev.step} of ${ev.of}`;
            [...dots.children].forEach((dot, i) => dot.classList.toggle("on", i < ev.step));
            break;
          case "coach":
            orb.dataset.coach = "true";
            coachTag.hidden = false;
            stepLabel.textContent = "Your coach";
            break;
          case "ended":
            clearInterval(clock);
            showResult(ev, invite);
            break;
          case "error":
            if (ev.code === "dropped") captions.textContent = "The connection dropped.";
            break;
          default:
            break;
        }
      },
    });
    try {
      await session.begin();
    } catch (err) {
      cleanupVisuals();
      toast(err.message, "error");
      showIncoming(invite);
      el.prepend(h("div", { class: "inline-error" }, icon("alert"), h("span", {}, err.message)));
    }
  }

  function cleanupVisuals() {
    cancelAnimationFrame(raf);
    viz?.stop();
  }

  function showResult(ev, invite) {
    cleanupVisuals();
    const passed = ev.outcome === "passed";
    const aborted = ev.outcome === "aborted";
    el.replaceChildren(
      h(
        "section",
        { class: `result ${passed ? "ok" : aborted ? "warn" : "bad"} rise` },
        h("div", { class: "result-i" }, icon(passed ? "check" : "alert")),
        h("h1", {}, passed ? "Well done! · शाबाश!" : aborted ? "The call ended early" : "Good that we practised"),
        h("p", { class: "lead" }, passed ? "You did not share anything. A real scammer would have stopped here with nothing." : aborted ? "No problem. You can try again whenever you like." : "In a real call, sharing that detail could have cost you money. That is exactly why we practise."),
        ev.debriefText ? h("p", { class: "debrief" }, ev.debriefText) : null,
        ev.redFlags?.length
          ? h("div", { class: "flags big" }, h("h2", {}, icon("shield"), "Remember these 3 things"), h("ol", {}, ev.redFlags.map((flag) => h("li", {}, flag))))
          : null,
        h("p", { class: "lead hi", lang: "hi" }, "असली कॉल में कभी OTP, पिन, आधार या पैसे न दें। कॉल काटकर अपने परिवार को फ़ोन करें।"),
        h("button", { class: "btn primary lg block", type: "button", onClick: () => startCall(invite) }, icon("rewind"), "Practise again"),
      ),
    );
  }

  return {
    el,
    destroy() {
      cleanupVisuals();
      if (session && session.state !== "ended") session.close();
    },
  };
}
