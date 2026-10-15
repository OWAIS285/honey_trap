// A raymarched 3D "voice orb" drawn by a fragment shader on a small canvas (no libraries, no assets).
// The surface ripples with the loudness you give it, follows the pointer, and glows in the tint you set.
// createOrb() returns null when WebGL2 is missing so callers keep their CSS fallback.

import { reducedMotion } from "./util.js";

const VERT = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }`;

const FRAG = `#version 300 es
precision highp float;
uniform vec2 uRes;
uniform float uTime;
uniform vec2 uMouse;
uniform float uEnergy;
uniform vec3 uTint;
out vec4 outColor;

mat2 rot(float a) { float c = cos(a), s = sin(a); return mat2(c, -s, s, c); }

float field(vec3 p) {
  float t = uTime;
  float d = sin(p.x * 2.1 + t * 0.9) * sin(p.y * 2.3 - t * 0.7) * sin(p.z * 2.0 + t * 1.1);
  d += 0.5 * sin(p.x * 4.3 - t * 1.3 + p.y * 3.1) * sin(p.z * 4.1 + t * 0.8 - p.x * 2.0);
  d += 0.25 * sin(p.y * 7.7 + t * 2.0 + p.z * 5.0) * sin(p.x * 7.1 - t * 1.7);
  return d * (0.06 + uEnergy * 0.15);
}

float map(vec3 p) { return length(p) - 1.0 - field(p); }

vec3 normalAt(vec3 p) {
  vec2 e = vec2(0.004, -0.004);
  return normalize(e.xyy * map(p + e.xyy) + e.yyx * map(p + e.yyx) + e.yxy * map(p + e.yxy) + e.xxx * map(p + e.xxx));
}

float hash(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void main() {
  vec2 uv = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y;
  vec3 ro = vec3(0.0, 0.0, 4.7);
  vec3 rd = normalize(vec3(uv, -1.6));
  mat2 ry = rot(uMouse.x * 0.55 + uTime * 0.1);
  mat2 rx = rot(-uMouse.y * 0.4);
  ro.xz = ry * ro.xz; rd.xz = ry * rd.xz;
  ro.yz = rx * ro.yz; rd.yz = rx * rd.yz;

  float b = dot(ro, rd);
  float closest = length(ro - rd * b);
  float edgeFade = 1.0 - smoothstep(0.3, 0.5, length(uv));
  float halo = exp(-max(closest - 0.95, 0.0) * 3.6) * (0.4 + uEnergy * 0.55) * edgeFade;
  float alpha = halo * 0.6;
  vec3 col = uTint * alpha;

  float disc = b * b - (dot(ro, ro) - 2.4);
  if (disc > 0.0) {
    float root = sqrt(disc);
    float t = -b - root;
    float tFar = -b + root;
    float minD = 10.0;
    bool hit = false;
    vec3 p = ro;
    for (int i = 0; i < 44; i++) {
      p = ro + rd * t;
      float d = map(p);
      minD = min(minD, d);
      if (d < 0.0015) { hit = true; break; }
      t += d * 0.55;
      if (t > tFar) break;
    }
    if (hit) {
      vec3 n = normalAt(p);
      float ndv = max(dot(n, -rd), 0.0);
      float fres = pow(1.0 - ndv, 2.6);
      vec3 L = normalize(vec3(-0.7, 0.8, 0.9));
      float diff = max(dot(n, L), 0.0);
      vec3 r = reflect(rd, n);
      float sky = smoothstep(-0.3, 0.9, r.y);
      float spec = pow(max(dot(r, L), 0.0), 60.0);
      float spec2 = pow(max(dot(r, normalize(vec3(0.8, -0.2, 0.6))), 0.0), 28.0) * 0.35;
      float bands = 0.5 + 0.5 * sin(field(p) * 55.0 + p.y * 5.0 - uTime * 1.4);
      float lines = smoothstep(0.78, 0.97, bands);
      vec3 c = vec3(0.01, 0.04, 0.15);
      c += vec3(0.04, 0.14, 0.42) * diff * 1.6;
      c += vec3(0.08, 0.26, 0.62) * sky * 0.9;
      c += uTint * fres * (1.4 + uEnergy);
      c += vec3(0.85, 0.95, 1.0) * (spec + spec2);
      c += uTint * lines * (0.3 + uEnergy * 0.8) * (0.4 + ndv);
      c = c / (1.0 + c * 0.35);
      col = pow(c, vec3(0.92));
      alpha = 1.0;
    } else {
      float edge = smoothstep(0.03, 0.0, minD) * 0.6;
      alpha = max(alpha, edge);
      col = uTint * alpha;
    }
  }
  col += (hash(gl_FragCoord.xy + uTime) - 0.5) * 0.012 * alpha;
  outColor = vec4(min(col, vec3(alpha)), alpha);
}`;

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.warn("orb shader:", gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

/**
 * @param {HTMLCanvasElement} canvas
 * @param {{ pointer?: boolean, tint?: number[], maxDpr?: number }} [options]
 */
export function createOrb(canvas, { pointer = true, tint = [0.35, 0.66, 1], maxDpr = 1.25 } = {}) {
  const gl = canvas.getContext("webgl2", { alpha: true, premultipliedAlpha: true, antialias: false, powerPreference: "low-power" });
  if (!gl) return null;
  const vs = compile(gl, gl.VERTEX_SHADER, VERT);
  const fs = compile(gl, gl.FRAGMENT_SHADER, FRAG);
  if (!vs || !fs) return null;
  const program = gl.createProgram();
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) return null;
  gl.useProgram(program);

  const buffer = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(program, "aPos");
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const u = Object.fromEntries(["uRes", "uTime", "uMouse", "uEnergy", "uTint"].map((name) => [name, gl.getUniformLocation(program, name)]));

  const state = { energy: 0.1, energyTarget: 0.1, mx: 0, my: 0, tx: 0, ty: 0, time: 0, tint: [...tint], tintTarget: [...tint] };
  let scale = 1;
  let raf = 0;
  let visible = true;
  let running = false;
  let last = performance.now();
  let slow = 0;
  let dead = false;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, maxDpr) * scale;
    const w = Math.max(2, Math.round(canvas.clientWidth * dpr));
    const h = Math.max(2, Math.round(canvas.clientHeight * dpr));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    gl.viewport(0, 0, w, h);
  }

  function draw() {
    gl.uniform2f(u.uRes, canvas.width, canvas.height);
    gl.uniform1f(u.uTime, state.time);
    gl.uniform2f(u.uMouse, state.mx, state.my);
    gl.uniform1f(u.uEnergy, state.energy);
    gl.uniform3f(u.uTint, state.tint[0], state.tint[1], state.tint[2]);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    state.energy += (state.energyTarget - state.energy) * Math.min(1, dt * 8);
    state.mx += (state.tx - state.mx) * Math.min(1, dt * 3);
    state.my += (state.ty - state.my) * Math.min(1, dt * 3);
    for (let i = 0; i < 3; i++) state.tint[i] += (state.tintTarget[i] - state.tint[i]) * Math.min(1, dt * 4);
    state.time += dt * (0.55 + state.energy * 1.3);
    draw();
    // Drop the resolution on slow GPUs instead of stuttering.
    slow = dt > 0.028 ? slow + 1 : Math.max(0, slow - 1);
    if (slow > 40 && scale > 0.5) {
      scale *= 0.8;
      slow = 0;
      resize();
    }
    raf = requestAnimationFrame(frame);
  }

  function sync() {
    const should = visible && !document.hidden && !dead && !reducedMotion();
    if (should && !running) {
      running = true;
      last = performance.now();
      raf = requestAnimationFrame(frame);
    } else if (!should && running) {
      running = false;
      cancelAnimationFrame(raf);
    }
  }

  const resizeObserver = new ResizeObserver(() => {
    resize();
    if (!running) draw();
  });
  resizeObserver.observe(canvas);
  const visibleObserver = new IntersectionObserver((entries) => {
    visible = entries[entries.length - 1].isIntersecting;
    sync();
  });
  visibleObserver.observe(canvas);
  const onVisibility = () => sync();
  document.addEventListener("visibilitychange", onVisibility);
  const onMove = (event) => {
    const rect = canvas.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    state.tx = Math.max(-1, Math.min(1, (event.clientX - cx) / Math.max(rect.width, 320)));
    state.ty = Math.max(-1, Math.min(1, (event.clientY - cy) / Math.max(rect.height, 320)));
  };
  if (pointer) window.addEventListener("pointermove", onMove, { passive: true });
  const onLost = (event) => {
    event.preventDefault();
    dead = true;
    sync();
    canvas.classList.add("is-lost");
  };
  canvas.addEventListener("webglcontextlost", onLost);

  resize();
  state.time = reducedMotion() ? 3 : Math.random() * 10;
  draw();
  sync();

  return {
    setEnergy(value) {
      state.energyTarget = Math.max(0, Math.min(1.2, value));
    },
    setTint(rgb) {
      state.tintTarget = [...rgb];
    },
    destroy() {
      dead = true;
      sync();
      resizeObserver.disconnect();
      visibleObserver.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onMove);
      canvas.removeEventListener("webglcontextlost", onLost);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
    },
  };
}
