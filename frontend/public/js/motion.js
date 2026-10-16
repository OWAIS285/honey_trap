// Page-level motion: word-by-word headline reveals, custom cursor, magnetic buttons, scroll progress,
// velocity marquee, the pinned "how it works" story and the route curtain.
// Everything is a no-op (or a plain static state) for people who prefer reduced motion.

import { h, logo, reducedMotion } from "./util.js";

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// ---------- split headlines ----------

/** Wrap every word in a masked span so it can rise into place. Elements inside the node keep their classes. */
export function splitWords(root) {
  let index = 0;
  const walk = (node) => {
    for (const child of [...node.childNodes]) {
      if (child.nodeType === Node.TEXT_NODE) {
        const frag = document.createDocumentFragment();
        for (const part of child.textContent.split(/(\s+)/)) {
          if (!part) continue;
          if (/^\s+$/.test(part)) frag.append(" ");
          else frag.append(h("span", { class: "sw", style: { "--i": index++ } }, h("span", { class: "sw-i" }, part)));
        }
        child.replaceWith(frag);
      } else if (child.nodeType === Node.ELEMENT_NODE) {
        child.classList.add("is-split");
        walk(child);
      }
    }
  };
  root.setAttribute("aria-label", root.textContent.replace(/\s+/g, " ").trim());
  walk(root);
  root.querySelectorAll(".sw").forEach((w) => w.setAttribute("aria-hidden", "true"));
  return root;
}

let splitObserver;
/** Split every [data-split] heading under root once and play it when it scrolls into view ([data-split="now"] plays at once). */
export function initSplit(root) {
  const items = [...root.querySelectorAll("[data-split]:not(.split-ready)")];
  for (const el of items) {
    splitWords(el);
    el.classList.add("split-ready");
    if (reducedMotion() || !("IntersectionObserver" in window)) el.classList.add("split-in");
    else if (el.dataset.split === "now") requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add("split-in")));
    else {
      splitObserver ||= new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            entry.target.classList.add("split-in");
            splitObserver.unobserve(entry.target);
          }
        },
        { threshold: 0.35 },
      );
      splitObserver.observe(el);
    }
  }
}

// ---------- cursor, magnetic buttons, scroll progress ----------

const HOVER_TARGET = "a, button, [role='tab'], summary, label, select, .chip.action, .chip.toggle, .mag";
const TEXT_TARGET = "input, textarea, [contenteditable='true']";

export function installCursor() {
  if (reducedMotion() || !window.matchMedia("(pointer: fine)").matches) return;
  const dot = h("i", { class: "cursor-dot" });
  const ring = h("i", { class: "cursor-ring" });
  const root = h("div", { class: "cursor", "aria-hidden": "true" }, ring, dot);
  document.body.append(root);
  document.documentElement.classList.add("has-cursor");
  let x = -100;
  let y = -100;
  let rx = -100;
  let ry = -100;
  let raf = 0;
  const loop = () => {
    rx += (x - rx) * 0.2;
    ry += (y - ry) * 0.2;
    dot.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    ring.style.transform = `translate3d(${rx}px, ${ry}px, 0)`;
    raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);
  window.addEventListener(
    "pointermove",
    (event) => {
      x = event.clientX;
      y = event.clientY;
      root.classList.add("on");
      const target = event.target instanceof Element ? event.target : null;
      root.classList.toggle("is-link", !!target?.closest(HOVER_TARGET));
      root.classList.toggle("is-text", !!target?.closest(TEXT_TARGET));
    },
    { passive: true },
  );
  document.addEventListener("pointerdown", () => root.classList.add("is-down"));
  document.addEventListener("pointerup", () => root.classList.remove("is-down"));
  document.documentElement.addEventListener("pointerleave", () => root.classList.remove("on"));
  document.addEventListener("visibilitychange", () => {
    cancelAnimationFrame(raf);
    if (!document.hidden) raf = requestAnimationFrame(loop);
  });
}

/** Buttons marked .btn.lg, .btn.xl or .mag lean towards the pointer. */
export function installMagnetic() {
  if (reducedMotion() || !window.matchMedia("(pointer: fine)").matches) return;
  let active = null;
  const release = () => {
    if (!active) return;
    active.style.setProperty("--tx", "0px");
    active.style.setProperty("--ty", "0px");
    active = null;
  };
  document.addEventListener(
    "pointermove",
    (event) => {
      const el = event.target instanceof Element ? event.target.closest(".btn.lg, .btn.xl, .mag") : null;
      if (el !== active) release();
      if (!el) return;
      active = el;
      const rect = el.getBoundingClientRect();
      const dx = event.clientX - (rect.left + rect.width / 2);
      const dy = event.clientY - (rect.top + rect.height / 2);
      el.style.setProperty("--tx", `${(dx * 0.22).toFixed(1)}px`);
      el.style.setProperty("--ty", `${(dy * 0.3).toFixed(1)}px`);
    },
    { passive: true },
  );
  document.addEventListener("pointerleave", release);
}

export function installScrollProgress() {
  const bar = h("div", { class: "progress", "aria-hidden": "true" }, h("i"));
  document.body.append(bar);
  const fill = bar.firstChild;
  let queued = false;
  const paint = () => {
    queued = false;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    fill.style.transform = `scaleX(${max > 0 ? clamp(window.scrollY / max, 0, 1) : 0})`;
    document.documentElement.classList.toggle("scrolled", window.scrollY > 24);
  };
  window.addEventListener(
    "scroll",
    () => {
      if (!queued) {
        queued = true;
        requestAnimationFrame(paint);
      }
    },
    { passive: true },
  );
  paint();
}

// ---------- velocity marquee ----------

/** Slides a duplicated track sideways; scrolling speeds it up and skews it. Returns a destroy function. */
export function velocityMarquee(track, { speed = 40 } = {}) {
  if (reducedMotion()) return () => {};
  let offset = 0;
  let lastY = window.scrollY;
  let velocity = 0;
  let last = performance.now();
  let raf = 0;
  const frame = (now) => {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    const dy = window.scrollY - lastY;
    lastY = window.scrollY;
    velocity += (clamp(dy, -80, 80) - velocity) * 0.12;
    offset -= (speed + Math.abs(velocity) * 22) * dt;
    const half = track.scrollWidth / 2 || 1;
    if (offset <= -half) offset += half;
    track.style.transform = `translate3d(${offset.toFixed(1)}px, 0, 0) skewX(${(-velocity * 0.12).toFixed(2)}deg)`;
    raf = requestAnimationFrame(frame);
  };
  raf = requestAnimationFrame(frame);
  const onVisibility = () => {
    cancelAnimationFrame(raf);
    if (!document.hidden) {
      last = performance.now();
      raf = requestAnimationFrame(frame);
    }
  };
  document.addEventListener("visibilitychange", onVisibility);
  return () => {
    cancelAnimationFrame(raf);
    document.removeEventListener("visibilitychange", onVisibility);
  };
}

// ---------- pinned story ----------

/** A tall section whose sticky child changes step as you scroll. Sets data-step and --p on the section. */
export function pinnedStory(section, steps, rails = []) {
  let queued = false;
  let step = -1;
  const paint = () => {
    queued = false;
    const rect = section.getBoundingClientRect();
    const span = Math.max(1, rect.height - window.innerHeight);
    const p = clamp(-rect.top / span, 0, 1);
    const next = Math.min(steps - 1, Math.floor(p * steps));
    section.style.setProperty("--p", p.toFixed(3));
    if (next !== step) {
      step = next;
      section.dataset.step = String(step);
      rails.forEach((rail, i) => {
        rail.classList.toggle("active", i === step);
        rail.classList.toggle("done", i < step);
        rail.setAttribute("aria-current", i === step ? "step" : "false");
      });
    }
  };
  const onScroll = () => {
    if (!queued) {
      queued = true;
      requestAnimationFrame(paint);
    }
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  paint();
  return {
    goTo(index) {
      const top = section.getBoundingClientRect().top + window.scrollY;
      const span = Math.max(1, section.offsetHeight - window.innerHeight);
      window.scrollTo({ top: top + span * ((index + 0.5) / steps), behavior: reducedMotion() ? "auto" : "smooth" });
    },
    destroy() {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    },
  };
}

// ---------- route curtain ----------

// Five staggered panels sweep up over the page, the page name rises in the middle, then the panels carry on upward.
export function createCurtain() {
  const panels = Array.from({ length: 5 }, (_, i) => h("i", { class: "cv-p", style: { "--i": i } }));
  const name = h("span", {});
  const el = h("div", { class: "curtain", "aria-hidden": "true" }, h("div", { class: "cv-panels" }, panels), h("div", { class: "curtain-mark" }, logo(), h("span", { class: "cv-label" }, name)));
  document.body.append(el);
  let state = "idle";
  let covering = null;
  return {
    cover(text = "") {
      if (reducedMotion()) return Promise.resolve();
      name.textContent = text;
      if (state === "covering") return covering;
      if (state === "covered") return Promise.resolve();
      state = "covering";
      el.className = "curtain on cover";
      covering = wait(720).then(() => {
        state = "covered";
        el.className = "curtain on covered";
      });
      return covering;
    },
    async uncover() {
      if (reducedMotion()) return;
      state = "uncovering";
      el.className = "curtain on uncover";
      await wait(640);
      if (state === "uncovering") {
        state = "idle";
        el.className = "curtain";
      }
    },
  };
}
