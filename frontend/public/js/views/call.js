// Live call (voice) and text chat views. Both drive the same dashboard from the server's event stream.

import { api } from "../api.js";
import { Visualizer } from "../audio.js";
import { strainCard } from "../components.js";
import { createDashboard } from "../dashboard.js";
import { CallSession } from "../session.js";
import { setEnergy } from "../fx.js";
import { createOrb } from "../orb3d.js";
import { fmtClock, fmtDuration, h, icon, toast, verdictTitle } from "../util.js";

export function CallView({ mode }) {
  const voice = mode === "voice";
  const dash = createDashboard({ callerLabel: "You, as the scammer", personaLabel: "Ramesh" });
  let session = null;
  let config = null;
  let maxSeconds = 300;
  let callId = null;
  let phoneLine = false;
  let level = 0;
  let raf = 0;
  let timer = null;
  let startedAt = 0;

  // ----- left column: the phone -----
  const status = h("p", { class: "call-status", "aria-live": "polite" }, "Ready when you are.");
  const orb = h(
    "div",
    { class: "orb-wrap", "data-state": "idle" },
    h("span", { class: "ring r1" }),
    h("span", { class: "ring r2" }),
    h("span", { class: "ring r3" }),
    h("div", { class: "avatar" }, h("span", {}, "RS")),
  );
  const glCanvas = h("canvas", { class: "orb-gl", "aria-hidden": "true" });
  orb.append(glCanvas);
  const orb3d = createOrb(glCanvas, { pointer: false });
  orb.classList.toggle("gl", !!orb3d);
  const BASE_ENERGY = { idle: 0.08, connecting: 0.45, listening: 0.18, speaking: 0.3, ended: 0 };
  const canvas = voice ? h("canvas", { class: "viz", "aria-hidden": "true" }) : null;
  const timerEl = h("div", { class: "call-timer" }, "00:00");
  const maxEl = h("span", {}, " / 05:00");
  timerEl.append(maxEl);

  const startBtn = h("button", { class: "btn primary lg block", type: "button", onClick: start }, icon(voice ? "phone" : "chat"), voice ? "Start the call" : "Start the chat");
  const muteBtn = h("button", { class: "btn round", type: "button", "aria-pressed": "false", "aria-label": "Mute microphone", onClick: toggleMute }, icon("mic"));
  const endBtn = h("button", { class: "btn danger round", type: "button", "aria-label": "Hang up", onClick: hangUp }, icon("hangup"));
  const lineBtn = h("button", { class: "chip toggle", type: "button", "aria-pressed": "false", onClick: toggleLine }, icon("phone"), "Old-phone sound");
  const controls = h("div", { class: "controls", hidden: true }, voice ? muteBtn : null, endBtn, voice ? lineBtn : null);

  const input = h("input", { class: "input", type: "text", maxlength: "500", autocomplete: "off", placeholder: voice ? "Or type a line instead of speaking…" : "Type what the scammer says…", "aria-label": "Type a line", disabled: true });
  const typeRow = h("form", { class: "type-row", onSubmit: submitTyped }, input, h("button", { class: "btn primary round sm", type: "submit", "aria-label": "Send", disabled: true }, icon("send")));
  const sendBtn = typeRow.querySelector("button");

  const note = h(
    "p",
    { class: "fineprint" },
    icon("lock"),
    voice
      ? "Your voice goes to Google's Gemini over a secure connection and the call is kept as a private recording for 14 days. Headphones stop echo."
      : "Messages go to Google's Gemini over a secure connection and the chat is kept privately for 14 days.",
  );
  const errorBox = h("div", { class: "inline-error", hidden: true });

  const phone = h(
    "section",
    { class: `card phone ${voice ? "" : "chat-mode"}` },
    h("div", { class: "phone-top" }, h("span", { class: "tag" }, voice ? "Live demo line" : "Text chat"), timerEl),
    orb,
    h("h2", { class: "persona-name" }, "Ramesh Sharma"),
    h("p", { class: "persona-sub" }, "68 · retired schoolteacher · Lucknow"),
    status,
    canvas,
    errorBox,
    startBtn,
    controls,
    typeRow,
    note,
  );

  const summarySlot = h("div", { class: "slot" });
  const strainSlot = h("div", { class: "slot" });
  const left = h("div", { class: "call-left" }, phone, summarySlot, strainSlot);
  const el = h("div", { class: `call-page ${voice ? "voice" : "text"}`, "data-state": "idle" }, left, dash.el);
  const modeSwitch = h(
    "div",
    { class: "seg", role: "tablist", "aria-label": "Choose how to talk to the decoy" },
    h("a", { class: `seg-item ${voice ? "active" : ""}`, href: "#/call", role: "tab", "aria-selected": String(voice) }, icon("mic"), "Voice call"),
    h("a", { class: `seg-item ${voice ? "" : "active"}`, href: "#/chat", role: "tab", "aria-selected": String(!voice) }, icon("chat"), "Text chat"),
  );
  const wrap = h("div", { class: "call-wrap" }, modeSwitch, el);

  const viz = voice ? new Visualizer(canvas, { frequency: () => session?.frequency() || null, micLevel: () => session?.micLevel() || 0 }) : null;
  viz?.start();

  const frame = () => {
    const target = session ? Math.max(session.personaLevel(), session.micLevel() * 0.8) : 0;
    level += (target - level) * 0.3;
    orb.style.setProperty("--level", level.toFixed(3));
    orb3d?.setEnergy((BASE_ENERGY[orb.dataset.state] ?? 0.1) + level * 1.1);
    setEnergy(level * 1.4);
    raf = requestAnimationFrame(frame);
  };
  frame();

  api
    .config()
    .then((c) => {
      config = c;
      maxSeconds = c.maxCallSeconds || maxSeconds;
      maxEl.textContent = ` / ${fmtClock(maxSeconds)}`;
      if (c.killSwitch) setError("Live sessions are paused right now. Please use the replay.");
    })
    .catch(() => {});

  // ----- state -----
  function setOrb(state) {
    orb.dataset.state = state;
  }

  function setUi(state) {
    el.dataset.state = state;
    const idle = state === "idle" || state === "ended";
    startBtn.hidden = !idle;
    startBtn.replaceChildren(icon(voice ? "phone" : "chat"), state === "ended" ? (voice ? "Call again" : "Chat again") : voice ? "Start the call" : "Start the chat");
    controls.hidden = state !== "live";
    const live = state === "live";
    input.disabled = !live;
    sendBtn.disabled = !live;
    if (state === "connecting") {
      setOrb("connecting");
      status.textContent = voice ? "Ringing…" : "Connecting…";
    } else if (state === "live") {
      status.textContent = voice ? "Ramesh picked up. Say something, you are the scammer." : "Ramesh is online. Type as the scammer.";
    } else if (state === "ending") {
      setOrb("connecting");
      stopTimer();
      status.textContent = "Hanging up. Building the evidence pack and strain card…";
    } else if (state === "ended") {
      setOrb("ended");
      status.textContent = "Call ended.";
    } else {
      setOrb("idle");
      status.textContent = "Ready when you are.";
    }
  }

  function setError(message) {
    errorBox.hidden = !message;
    const nodes = [icon("alert"), h("span", {}, message)];
    if (message && message.includes("microphone")) nodes.push(h("a", { href: "#/chat", class: "btn mini" }, "Use text chat"));
    errorBox.replaceChildren(...nodes);
  }

  function startTimer() {
    clearInterval(timer);
    startedAt = performance.now();
    timer = setInterval(() => {
      const seconds = (performance.now() - startedAt) / 1000;
      timerEl.firstChild.textContent = fmtClock(seconds);
      timerEl.classList.toggle("warn", maxSeconds - seconds < 30);
    }, 500);
  }

  function stopTimer() {
    clearInterval(timer);
    timer = null;
  }

  // ----- actions -----
  async function start() {
    if (session && session.state !== "ended") return;
    if (config?.killSwitch) {
      toast("Live sessions are paused. Please use the replay.", "error");
      return;
    }
    dash.reset();
    summarySlot.replaceChildren();
    strainSlot.replaceChildren();
    setError("");
    callId = null;
    timerEl.firstChild.textContent = "00:00";
    const created = new CallSession({ path: voice ? "/ws/call" : "/ws/text", start: {}, voice, onEvent, onState: (s) => s !== "idle" && setUi(s) });
    session = created;
    created.player?.setPhoneLine(phoneLine);
    muteBtn.setAttribute("aria-pressed", "false");
    muteBtn.replaceChildren(icon("mic"));
    try {
      await created.begin();
    } catch (err) {
      session = null;
      stopTimer();
      setUi("idle");
      setError(err.message);
      toast(err.message, "error");
    }
  }

  function hangUp() {
    session?.end();
  }

  function toggleMute() {
    if (!session) return;
    const muted = !session.muted;
    session.setMuted(muted);
    muteBtn.setAttribute("aria-pressed", String(muted));
    muteBtn.classList.toggle("on", muted);
    muteBtn.replaceChildren(icon(muted ? "micoff" : "mic"));
  }

  function toggleLine() {
    phoneLine = !phoneLine;
    session?.setPhoneLine(phoneLine);
    lineBtn.setAttribute("aria-pressed", String(phoneLine));
    lineBtn.classList.toggle("on", phoneLine);
  }

  function sendLine(text) {
    if (!session || session.state !== "live") {
      toast(voice ? "Start the call first, then send the line." : "Start the chat first, then send the line.", "error");
      return;
    }
    session.sendText(text);
    if (!voice) {
      status.textContent = "Ramesh is typing…";
      setOrb("speaking");
    }
  }

  function submitTyped(event) {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    sendLine(text);
    input.value = "";
  }

  function onEvent(ev) {
    if (ev.type === "persona_audio") {
      if (session?.state === "live") setOrb(ev.playing ? "speaking" : "listening");
      return;
    }
    dash.handle(ev);
    switch (ev.type) {
      case "ready":
        callId = ev.callId;
        maxSeconds = ev.maxSeconds || maxSeconds;
        maxEl.textContent = ` / ${fmtClock(maxSeconds)}`;
        dash.startClock();
        startTimer();
        setOrb("listening");
        break;
      case "transcript":
        if (!voice && ev.speaker === "persona") {
          setOrb(ev.final ? "listening" : "speaking");
          if (ev.final) status.textContent = "Ramesh is online. Type as the scammer.";
        }
        break;
      case "ended":
        stopTimer();
        showSummary(ev);
        break;
      case "error":
        stopTimer();
        setError(ev.message || "Something went wrong.");
        if (callId) showSummary({ reason: "error", counts: {}, durationSec: (performance.now() - startedAt) / 1000 });
        break;
      default:
        break;
    }
  }

  function showSummary(ev) {
    const metric = (label, value) => h("div", { class: "metric" }, h("b", {}, value), h("span", {}, label));
    const counts = ev.counts || {};
    summarySlot.replaceChildren(
      h(
        "section",
        { class: "card summary rise" },
        h("div", { class: "card-h" }, icon("check"), "Call complete"),
        h(
          "div",
          { class: "metrics" },
          metric("time wasted", fmtDuration(ev.durationSec)),
          ev.verdict ? metric("verdict", verdictTitle(ev.verdict, ev.scamType)) : null,
          metric("details caught", `${counts.details ?? 0} (${counts.confirmed ?? 0} confirmed)`),
          metric("recording", ev.recording ? "saved" : "none"),
          ev.estCostUsd != null ? metric("estimated AI cost", `$${Number(ev.estCostUsd).toFixed(3)}`) : null,
        ),
        h(
          "div",
          { class: "cta-row" },
          callId ? h("a", { class: "btn primary", href: `#/call/${callId}` }, icon("file"), "Open call review") : null,
          ev.strainId ? h("a", { class: "btn", href: `#/drill/new/${ev.strainId}` }, icon("users"), "Create family drill") : null,
        ),
      ),
    );
    if (ev.strain) strainSlot.replaceChildren(strainCard({ ...ev.strain, strainId: ev.strainId }, { onDrill: ev.strainId ? () => (location.hash = `#/drill/new/${ev.strainId}`) : null }));
  }

  return {
    el: wrap,
    destroy() {
      cancelAnimationFrame(raf);
      setEnergy(0);
      orb3d?.destroy();
      stopTimer();
      viz?.stop();
      dash.stopClock();
      if (session && session.state !== "ended") session.close();
    },
  };
}
