// Cinematic opening: an unknown number rings, the decoy picks up, a voice ring wakes and the name resolves.
// Plays once per browser session on the landing page; any key, click or the Skip button ends it.

import { BRAND } from "./brand.js";
import { h, logo, reducedMotion } from "./util.js";

const SEEN_KEY = "intro-seen";
const T_PICK = 1.9; // seconds: the decoy picks up
const T_NAME = 2.55; // the name resolves
const T_OUT = 4.5; // the curtain lifts

export function shouldPlayIntro() {
  const flag = new URLSearchParams(location.search).get("intro");
  if (flag === "1") return true;
  if (flag === "0" || reducedMotion()) return false;
  const route = location.hash.replace(/\/+$/, "");
  if (route && route !== "#") return false;
  try {
    return !sessionStorage.getItem(SEEN_KEY);
  } catch {
    return true;
  }
}

export function playIntro({ onReveal } = {}) {
  return new Promise((resolve) => {
    const canvas = h("canvas", { class: "intro-canvas", "aria-hidden": "true" });
    const status = h("span", { class: "ic-status" }, "Incoming call · Unknown number");
    const flag = h("span", { class: "ic-flag" }, "Possible scam");
    const chip = h("div", { class: "intro-chip" }, h("span", { class: "ic-dot" }), status, flag);
    const letters = [...BRAND.name].map((ch, i) => h("span", { class: "il", "aria-hidden": "true", style: { "--i": i } }, ch === " " ? "\u00a0" : ch));
    const name = h("h1", { class: "intro-name", "aria-label": BRAND.name }, letters);
    const tag = h("p", { class: "intro-tag" }, BRAND.introLine);
    const mark = h("div", { class: "intro-mark", "aria-hidden": "true" }, logo());
    const skip = h("button", { class: "intro-skip", type: "button" }, "Skip intro");
    const root = h("div", { class: "intro", role: "dialog", "aria-label": `${BRAND.name} intro` }, canvas, h("div", { class: "intro-core" }, chip, mark, h("div", { class: "intro-text" }, name, tag)), skip);

    document.body.classList.add("intro-active");
    document.body.append(root);
    skip.focus({ preventScroll: true });

    const g = canvas.getContext("2d");
    let dpr = 1;
    let width = 0;
    let height = 0;
    let raf = 0;
    let finished = false;
    const timers = [];
    const t0 = performance.now();

    function resize() {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    }

    const ease = (k) => 1 - Math.pow(1 - Math.max(0, Math.min(1, k)), 3);

    function draw(now) {
      const t = (now - t0) / 1000;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, width, height);
      const cx = width / 2;
      const cy = height / 2;
      const scale = Math.min(1, Math.min(width, height) / 620);

      // Ringing: soft rings leave the phone.
      for (const start of [0.1, 0.62, 1.14]) {
        const life = (t - start) / 1.6;
        if (life <= 0 || life >= 1) continue;
        g.strokeStyle = `rgba(${start === 0.62 ? "90,169,255" : "56,189,248"},${(1 - life) * 0.5})`;
        g.lineWidth = 1.6;
        g.beginPath();
        g.arc(cx, cy, (34 + life * 250) * scale, 0, Math.PI * 2);
        g.stroke();
      }

      // Pick-up: a bright burst.
      const burst = (t - T_PICK) / 0.9;
      if (burst > 0 && burst < 1) {
        g.strokeStyle = `rgba(255,255,255,${(1 - burst) * 0.7})`;
        g.lineWidth = 3 * (1 - burst) + 0.5;
        g.beginPath();
        g.arc(cx, cy, (40 + ease(burst) * 420) * scale, 0, Math.PI * 2);
        g.stroke();
        const flash = g.createRadialGradient(cx, cy, 0, cx, cy, 260 * scale);
        flash.addColorStop(0, `rgba(110,180,255,${(1 - burst) * 0.35})`);
        flash.addColorStop(1, "rgba(110,180,255,0)");
        g.fillStyle = flash;
        g.fillRect(0, 0, width, height);
      }

      // The voice ring.
      const since = t - T_PICK;
      if (since > 0) {
        const env = ease(since / 0.8) * (t > T_OUT - 0.2 ? Math.max(0, 1 - (t - (T_OUT - 0.2)) / 0.4) : 1);
        const base = (58 + 22 * ease(since / 0.9) + (t > T_NAME ? Math.sin(t * 5) * 1.6 : 0)) * scale;
        const points = 132;
        const gradient = g.createLinearGradient(cx - base, cy - base, cx + base, cy + base);
        gradient.addColorStop(0, "#38bdf8");
        gradient.addColorStop(0.5, "#5aa9ff");
        gradient.addColorStop(1, "#2563eb");
        for (const [mult, alpha, width2] of [[1, 1, 2.6], [1.2, 0.3, 1.4]]) {
          g.beginPath();
          for (let i = 0; i <= points; i++) {
            const a = (i / points) * Math.PI * 2 + t * 0.35;
            const wobble = (0.5 + 0.5 * Math.sin(i * 0.41 + t * 5.2)) * (0.6 + 0.4 * Math.sin(i * 0.13 - t * 3.3));
            const r = (base + wobble * 26 * env * scale) * mult;
            const x = cx + Math.cos(a) * r;
            const y = cy + Math.sin(a) * r;
            if (i === 0) g.moveTo(x, y);
            else g.lineTo(x, y);
          }
          g.closePath();
          g.globalAlpha = alpha * Math.min(1, env * 1.4);
          g.strokeStyle = gradient;
          g.lineWidth = width2;
          g.shadowColor = "rgba(90,169,255,0.9)";
          g.shadowBlur = 18;
          g.stroke();
        }
        g.globalAlpha = 1;
        g.shadowBlur = 0;
        for (let k = 0; k < 3; k++) {
          const a = t * (0.9 + k * 0.25) + (k * Math.PI * 2) / 3;
          const r = (base + 38 * scale) * (1 + k * 0.08);
          g.fillStyle = ["#38bdf8", "#5aa9ff", "#2563eb"][k];
          g.globalAlpha = 0.85 * env;
          g.beginPath();
          g.arc(cx + Math.cos(a) * r, cy + Math.sin(a) * r, 2.6, 0, Math.PI * 2);
          g.fill();
        }
        g.globalAlpha = 1;
      }
      raf = requestAnimationFrame(draw);
    }

    function at(seconds, fn) {
      timers.push(setTimeout(fn, seconds * 1000));
    }

    function finish() {
      if (finished) return;
      finished = true;
      timers.forEach(clearTimeout);
      root.classList.add("p-out");
      try {
        sessionStorage.setItem(SEEN_KEY, "1");
      } catch {
        /* private mode: the intro may play again, which is harmless */
      }
      onReveal?.();
      document.body.classList.remove("intro-active");
      window.removeEventListener("resize", resize);
      window.removeEventListener("keydown", onKey);
      setTimeout(() => {
        cancelAnimationFrame(raf);
        root.remove();
        resolve();
      }, 900);
    }

    const onKey = (event) => {
      if (["Escape", "Enter", " "].includes(event.key)) {
        event.preventDefault();
        finish();
      }
    };

    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("keydown", onKey);
    root.addEventListener("pointerdown", finish);
    raf = requestAnimationFrame(draw);

    root.classList.add("p-ring");
    at(T_PICK, () => {
      root.classList.add("p-pick");
      status.textContent = "Decoy picked up";
      flag.textContent = "Recording";
    });
    at(T_NAME, () => root.classList.add("p-name"));
    at(T_OUT, finish);
  });
}
