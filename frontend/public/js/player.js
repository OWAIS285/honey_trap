// Recording player: stereo recording (caller left, persona right) mixed to the centre, two-lane waveform, click-to-seek.

import { fmtClock, h, icon } from "./util.js";

const SPEEDS = [1, 1.25, 1.5, 0.75];

export function createAudioPlayer({ blob, callerLabel = "Caller", personaLabel = "Ramesh", onFrame, onEnded } = {}) {
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  audio.preload = "auto";

  const playBtn = h("button", { class: "btn primary round", type: "button", "aria-label": "Play" }, icon("play"));
  const backBtn = h("button", { class: "btn ghost sm", type: "button", "aria-label": "Back 5 seconds" }, icon("rewind"), "5s");
  const speedBtn = h("button", { class: "btn ghost sm", type: "button", "aria-label": "Playback speed" }, "1x");
  const current = h("b", {}, "00:00");
  const total = h("span", {}, "00:00");
  const canvas = h("canvas", { class: "wave", tabindex: "0", role: "slider", "aria-label": "Seek in recording", "aria-valuemin": "0" });
  const el = h(
    "div",
    { class: "card player" },
    h("div", { class: "player-top" }, playBtn, h("div", { class: "player-time" }, current, " / ", total), h("span", { class: "grow" }), backBtn, speedBtn),
    canvas,
    h("div", { class: "lane-legend" }, h("span", { class: "dot caller" }), callerLabel, h("span", { class: "dot persona" }), personaLabel),
  );

  let peaks = null;
  let mixCtx = null;
  let raf = 0;
  let speedIndex = 0;

  function duration() {
    return Number.isFinite(audio.duration) ? audio.duration : 0;
  }

  function setPlayIcon() {
    playBtn.replaceChildren(icon(audio.paused ? "play" : "pause"));
    playBtn.setAttribute("aria-label", audio.paused ? "Play" : "Pause");
  }

  function draw() {
    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (!width || !height) return;
    if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
    }
    const g = canvas.getContext("2d");
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, width, height);
    const progress = duration() ? audio.currentTime / duration() : 0;
    const bins = peaks ? peaks[0].length : 0;
    const laneHeight = height / 2 - 3;
    const barWidth = bins ? width / bins : 0;
    const lanes = [
      { data: peaks && peaks[0], centre: height * 0.25, bright: "#6fe3ff", dim: "rgba(111,227,255,.28)" },
      { data: peaks && peaks[1], centre: height * 0.75, bright: "#ffb629", dim: "rgba(255,182,41,.28)" },
    ];
    for (const lane of lanes) {
      g.fillStyle = "rgba(255,255,255,.05)";
      g.fillRect(0, lane.centre - 0.5, width, 1);
      if (!lane.data) continue;
      for (let i = 0; i < bins; i++) {
        const amp = Math.max(1.5, lane.data[i] * laneHeight);
        g.fillStyle = (i + 0.5) / bins <= progress ? lane.bright : lane.dim;
        g.beginPath();
        g.roundRect(i * barWidth + 0.5, lane.centre - amp, Math.max(1, barWidth - 1.5), amp * 2, 1.5);
        g.fill();
      }
    }
    const x = progress * width;
    g.fillStyle = "#fff";
    g.fillRect(x - 1, 0, 2, height);
    g.beginPath();
    g.arc(x, 4, 4, 0, Math.PI * 2);
    g.fill();
    canvas.setAttribute("aria-valuemax", String(Math.round(duration())));
    canvas.setAttribute("aria-valuenow", String(Math.round(audio.currentTime)));
  }

  function updateTime() {
    current.textContent = fmtClock(audio.currentTime);
    total.textContent = fmtClock(duration());
    draw();
    onFrame?.(audio.currentTime);
  }

  function loop() {
    updateTime();
    if (!audio.paused) raf = requestAnimationFrame(loop);
  }

  function seek(seconds) {
    audio.currentTime = Math.max(0, Math.min(duration() || seconds, seconds));
    updateTime();
  }

  async function play() {
    if (mixCtx?.state === "suspended") await mixCtx.resume();
    await audio.play();
  }

  playBtn.addEventListener("click", () => (audio.paused ? play().catch(() => {}) : audio.pause()));
  backBtn.addEventListener("click", () => seek(audio.currentTime - 5));
  speedBtn.addEventListener("click", () => {
    speedIndex = (speedIndex + 1) % SPEEDS.length;
    audio.playbackRate = SPEEDS[speedIndex];
    speedBtn.textContent = `${SPEEDS[speedIndex]}x`;
  });
  audio.addEventListener("play", () => {
    setPlayIcon();
    cancelAnimationFrame(raf);
    loop();
  });
  audio.addEventListener("pause", () => {
    setPlayIcon();
    updateTime();
  });
  audio.addEventListener("ended", () => {
    setPlayIcon();
    updateTime();
    onEnded?.();
  });
  audio.addEventListener("loadedmetadata", updateTime);
  audio.addEventListener("seeked", updateTime);

  const seekFromPointer = (event) => {
    const rect = canvas.getBoundingClientRect();
    seek(((event.clientX - rect.left) / rect.width) * duration());
  };
  canvas.addEventListener("pointerdown", (event) => {
    canvas.setPointerCapture(event.pointerId);
    seekFromPointer(event);
    const move = (e) => seekFromPointer(e);
    const up = () => {
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up);
    };
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up);
  });
  canvas.addEventListener("keydown", (event) => {
    if (event.key === "ArrowRight") seek(audio.currentTime + 5);
    else if (event.key === "ArrowLeft") seek(audio.currentTime - 5);
    else if (event.key === " ") {
      event.preventDefault();
      playBtn.click();
    }
  });
  const resizeObserver = new ResizeObserver(draw);
  resizeObserver.observe(canvas);

  // Mix the stereo recording to the centre so both speakers are heard in both ears.
  try {
    mixCtx = new AudioContext();
    const source = mixCtx.createMediaElementSource(audio);
    const splitter = mixCtx.createChannelSplitter(2);
    const merger = mixCtx.createChannelMerger(2);
    const left = mixCtx.createGain();
    const right = mixCtx.createGain();
    left.gain.value = right.gain.value = 0.8;
    source.connect(splitter);
    splitter.connect(left, 0);
    splitter.connect(right, 1);
    left.connect(merger, 0, 0);
    left.connect(merger, 0, 1);
    right.connect(merger, 0, 0);
    right.connect(merger, 0, 1);
    merger.connect(mixCtx.destination);
  } catch {
    mixCtx = null;
  }

  // Waveform peaks.
  (async () => {
    try {
      const decodeCtx = new AudioContext();
      const decoded = await decodeCtx.decodeAudioData(await blob.arrayBuffer());
      decodeCtx.close().catch(() => {});
      const bins = 220;
      const lanes = [0, 1].map((channel) => {
        const data = decoded.getChannelData(Math.min(channel, decoded.numberOfChannels - 1));
        const step = Math.max(1, Math.floor(data.length / bins));
        const out = new Float32Array(bins);
        for (let i = 0; i < bins; i++) {
          let max = 0;
          for (let j = i * step; j < Math.min(data.length, (i + 1) * step); j += 8) max = Math.max(max, Math.abs(data[j]));
          out[i] = max;
        }
        return out;
      });
      const globalMax = Math.max(0.05, ...lanes[0], ...lanes[1]);
      peaks = lanes.map((lane) => lane.map((v) => Math.min(1, v / globalMax)));
      total.textContent = fmtClock(decoded.duration);
      draw();
    } catch {
      peaks = null;
    }
  })();

  function destroy() {
    cancelAnimationFrame(raf);
    audio.pause();
    resizeObserver.disconnect();
    mixCtx?.close().catch(() => {});
    URL.revokeObjectURL(url);
  }

  setTimeout(draw, 0);
  return { el, audio, play, pause: () => audio.pause(), seek, destroy, get time() { return audio.currentTime; } };
}
