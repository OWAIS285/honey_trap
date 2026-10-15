// Ambient visuals: a drifting signal network with voice-wave ribbons behind every page, plus pointer-driven glow and tilt.
// Everything pauses when the tab is hidden and collapses to a still frame for people who prefer reduced motion.

import { reducedMotion } from "./util.js";

const COLORS = ["56,189,248", "90,169,255", "37,99,235"];
let energyTarget = 0;

/** 0 to 1: how lively the background should feel (the call view raises it while someone speaks). */
export function setEnergy(value) {
  energyTarget = Math.max(0, Math.min(1, value));
}

export function startBackground(canvas) {
  const g = canvas.getContext("2d");
  const pointer = { x: -999, y: -999 };
  let width = 0;
  let height = 0;
  let dpr = 1;
  let nodes = [];
  let pings = [];
  let nextPing = 1.2;
  let energy = 0;
  let raf = 0;
  let last = performance.now();
  let clock = 0;

  function resize() {
    dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const count = Math.max(22, Math.min(64, Math.round((width * height) / 30000)));
    nodes = Array.from({ length: count }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.22,
      vy: (Math.random() - 0.5) * 0.22,
      r: 0.8 + Math.random() * 1.6,
      c: COLORS[Math.floor(Math.random() * COLORS.length)],
    }));
  }

  function ribbon(t, base, amp, freq, speed, color, alpha) {
    g.beginPath();
    const lift = 1 + energy * 2.2;
    for (let x = 0; x <= width + 8; x += 8) {
      const y = base + Math.sin(x * freq + t * speed) * amp * lift + Math.sin(x * freq * 2.3 - t * speed * 0.7) * amp * 0.35 * lift;
      if (x === 0) g.moveTo(x, y);
      else g.lineTo(x, y);
    }
    g.strokeStyle = `rgba(${color},${alpha + energy * 0.12})`;
    g.lineWidth = 1.6;
    g.stroke();
  }

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    clock += dt;
    energy += (energyTarget - energy) * 0.04;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, width, height);

    for (const n of nodes) {
      n.x += n.vx * dt * 60;
      n.y += n.vy * dt * 60;
      if (n.x < -20) n.x = width + 20;
      else if (n.x > width + 20) n.x = -20;
      if (n.y < -20) n.y = height + 20;
      else if (n.y > height + 20) n.y = -20;
      const dx = n.x - pointer.x;
      const dy = n.y - pointer.y;
      const d2 = dx * dx + dy * dy;
      if (d2 < 22000 && d2 > 1) {
        const push = (1 - d2 / 22000) * 0.9;
        n.x += (dx / Math.sqrt(d2)) * push;
        n.y += (dy / Math.sqrt(d2)) * push;
      }
    }

    g.lineWidth = 1;
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const d2 = dx * dx + dy * dy;
        if (d2 < 17000) {
          g.strokeStyle = `rgba(${a.c},${(1 - d2 / 17000) * (0.16 + energy * 0.14)})`;
          g.beginPath();
          g.moveTo(a.x, a.y);
          g.lineTo(b.x, b.y);
          g.stroke();
        }
      }
    }
    for (const n of nodes) {
      g.fillStyle = `rgba(${n.c},0.55)`;
      g.beginPath();
      g.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      g.fill();
    }

    nextPing -= dt;
    if (nextPing <= 0 && pings.length < 3 && nodes.length) {
      const n = nodes[Math.floor(Math.random() * nodes.length)];
      pings.push({ x: n.x, y: n.y, age: 0, c: n.c });
      nextPing = 2.6 + Math.random() * 3.2 - energy * 1.6;
    }
    pings = pings.filter((p) => p.age < 3.2);
    for (const p of pings) {
      p.age += dt;
      const k = p.age / 3.2;
      g.strokeStyle = `rgba(${p.c},${(1 - k) * 0.35})`;
      g.lineWidth = 1.4;
      g.beginPath();
      g.arc(p.x, p.y, 8 + k * 230, 0, Math.PI * 2);
      g.stroke();
    }

    const t = clock;
    ribbon(t, height * 0.86, 16, 0.006, 0.9, "56,189,248", 0.1);
    ribbon(t, height * 0.9, 20, 0.0045, -0.7, "90,169,255", 0.12);
    ribbon(t, height * 0.94, 13, 0.008, 1.2, "37,99,235", 0.14);

    if (pointer.x > -900) {
      const glow = g.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, 240);
      glow.addColorStop(0, "rgba(90,169,255,0.13)");
      glow.addColorStop(1, "rgba(90,169,255,0)");
      g.fillStyle = glow;
      g.fillRect(pointer.x - 240, pointer.y - 240, 480, 480);
    }
  }

  function loop(now) {
    frame(now);
    raf = requestAnimationFrame(loop);
  }

  function play() {
    cancelAnimationFrame(raf);
    last = performance.now();
    raf = requestAnimationFrame(loop);
  }

  resize();
  window.addEventListener("resize", resize);
  window.addEventListener("pointermove", (event) => {
    pointer.x = event.clientX;
    pointer.y = event.clientY;
  });
  document.addEventListener("pointerleave", () => {
    pointer.x = pointer.y = -999;
  });
  document.addEventListener("visibilitychange", () => (document.hidden ? cancelAnimationFrame(raf) : !reducedMotion() && play()));
  if (reducedMotion()) frame(performance.now());
  else play();
}

/** Card spotlight that follows the cursor and a gentle 3D tilt on `.tilt` elements. */
export function installPointerFx() {
  if (reducedMotion()) return;
  let latest = null;
  let queued = false;
  const apply = (e) => {
    const card = e.target.closest?.(".card");
    if (card) {
      const rect = card.getBoundingClientRect();
      card.style.setProperty("--mx", `${e.clientX - rect.left}px`);
      card.style.setProperty("--my", `${e.clientY - rect.top}px`);
    }
    const tilt = e.target.closest?.(".tilt");
    document.querySelectorAll(".tilt.is-tilting").forEach((el) => el !== tilt && resetTilt(el));
    if (tilt) {
      const rect = tilt.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width - 0.5;
      const py = (e.clientY - rect.top) / rect.height - 0.5;
      tilt.classList.add("is-tilting");
      tilt.style.setProperty("--ry", `${(px * 9).toFixed(2)}deg`);
      tilt.style.setProperty("--rx", `${(-py * 7).toFixed(2)}deg`);
    }
  };
  document.addEventListener("pointermove", (event) => {
    latest = event;
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      apply(latest);
    });
  });
  document.addEventListener("pointerleave", () => document.querySelectorAll(".tilt.is-tilting").forEach(resetTilt));
}

function resetTilt(el) {
  el.classList.remove("is-tilting");
  el.style.setProperty("--rx", "0deg");
  el.style.setProperty("--ry", "0deg");
}
