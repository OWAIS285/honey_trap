// One live session (voice call, text chat or family drill): owns the WebSocket, the microphone and the playback queue.

import { MIC_THRESHOLD, Mic, Player, ringTone } from "./audio.js";
import { clientId, wsUrl } from "./api.js";

export class SessionError extends Error {
  constructor(message, code) {
    super(message);
    this.code = code;
  }
}

function micMessage(err) {
  if (err?.name === "NotAllowedError" || err?.name === "SecurityError") {
    return "Microphone access was blocked. Allow the microphone in your browser, or use the typed chat instead.";
  }
  if (err?.name === "NotFoundError" || err?.name === "OverconstrainedError") {
    return "No microphone was found on this device. You can use the typed chat instead.";
  }
  return "The microphone could not be started. You can use the typed chat instead.";
}

export class CallSession {
  /**
   * @param {{path: string, start: object, voice: boolean, onEvent: (e: object) => void, onState?: (s: string) => void}} opts
   */
  constructor({ path, start, voice, onEvent, onState }) {
    this.path = path;
    this.startPayload = start;
    this.voice = voice;
    this.onEvent = onEvent;
    this.onState = onState || (() => {});
    this.state = "idle";
    this.ws = null;
    this.mic = null;
    this.player = voice ? new Player() : null;
    this.ready = false;
    this.ended = false;
    this.speechMs = 0;
    this.lastSpeechAt = 0;
    this.stopRing = null;
    this.muted = false;
  }

  setState(state) {
    this.state = state;
    this.onState(state);
  }

  async begin() {
    this.setState("connecting");
    if (this.voice) {
      await this.player.init();
      this.player.onStart = () => this.onEvent({ type: "persona_audio", playing: true });
      this.player.onIdle = () => this.onEvent({ type: "persona_audio", playing: false });
      this.mic = new Mic((pcm, rms) => this.onMicChunk(pcm, rms));
      try {
        await this.mic.start();
      } catch (err) {
        this.cleanup();
        this.setState("idle");
        throw new SessionError(micMessage(err), "mic");
      }
      try {
        this.stopRing = ringTone(this.player.ctx);
      } catch {
        this.stopRing = null;
      }
    }

    await new Promise((resolve, reject) => {
      let settled = false;
      const timer = setTimeout(() => {
        if (!settled) {
          settled = true;
          this.close();
          reject(new SessionError("The server did not answer in time. Please try again.", "timeout"));
        }
      }, 20000);
      const ws = new WebSocket(wsUrl(this.path));
      ws.binaryType = "arraybuffer";
      this.ws = ws;
      ws.onopen = () => ws.send(JSON.stringify({ type: "start", clientId: clientId(), ...this.startPayload }));
      ws.onmessage = (event) => {
        if (typeof event.data !== "string") return this.onAudio(event.data);
        let message;
        try {
          message = JSON.parse(event.data);
        } catch {
          return;
        }
        if (!settled && message.type === "ready") {
          settled = true;
          clearTimeout(timer);
          this.ready = true;
          this.setState("live");
          resolve();
        } else if (!settled && message.type === "error") {
          settled = true;
          clearTimeout(timer);
          this.cleanup();
          this.setState("idle");
          reject(new SessionError(message.message || "The call could not start.", message.code || "error"));
          return;
        }
        this.onServerEvent(message);
      };
      ws.onerror = () => {
        if (!settled) {
          settled = true;
          clearTimeout(timer);
          this.cleanup();
          this.setState("idle");
          reject(new SessionError("Could not connect to the server. Please try again.", "connect"));
        }
      };
      ws.onclose = () => {
        clearTimeout(timer);
        if (!settled) {
          settled = true;
          this.cleanup();
          this.setState("idle");
          reject(new SessionError("The connection closed before the call started.", "closed"));
          return;
        }
        if (!this.ended) {
          this.ended = true;
          this.onEvent({ type: "error", code: "dropped", message: "The connection dropped." });
          this.finish();
        }
      };
    });
  }

  onServerEvent(message) {
    if (message.type === "interrupted") this.player?.flush();
    this.onEvent(message);
    if (message.type === "ended") {
      this.ended = true;
      this.finish();
    }
  }

  onAudio(buffer) {
    this.stopRing?.();
    this.stopRing = null;
    if (!this.player) return;
    const firstOfTurn = !this.player.isPlaying();
    if (firstOfTurn && this.speechMs >= 320 && this.lastSpeechAt) {
      const ms = performance.now() - this.lastSpeechAt;
      if (ms > 0 && ms < 15000) this.send({ type: "latency", ms: Math.round(ms) });
      this.speechMs = 0;
      this.lastSpeechAt = 0;
    }
    this.player.enqueue(buffer);
  }

  onMicChunk(pcm, rms) {
    if (!this.ready || this.ws?.readyState !== WebSocket.OPEN) return;
    this.ws.send(pcm);
    if (this.player?.isPlaying()) {
      this.speechMs = 0;
    } else if (rms > MIC_THRESHOLD) {
      this.speechMs += 40;
      this.lastSpeechAt = performance.now();
    } else if (performance.now() - this.lastSpeechAt > 2500) {
      this.speechMs = 0;
    }
  }

  send(obj) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(obj));
  }

  sendText(text) {
    this.send({ type: "text", text });
  }

  setMuted(muted) {
    this.muted = muted;
    this.mic?.setMuted(muted);
  }

  setPhoneLine(on) {
    this.player?.setPhoneLine(on);
  }

  micLevel() {
    return this.mic?.level || 0;
  }

  personaLevel() {
    return this.player?.level() || 0;
  }

  frequency() {
    return this.player?.frequency() || null;
  }

  /** Ask the server to wrap up; it answers with an "ended" event after building the evidence and strain. */
  end() {
    if (this.ended || this.state === "ending") return;
    this.setState("ending");
    this.mic?.stop();
    this.send({ type: "end" });
    setTimeout(() => {
      if (!this.ended) this.close();
    }, 45000);
  }

  close() {
    try {
      this.ws?.close();
    } catch {
      /* ignore */
    }
    this.cleanup();
  }

  finish() {
    this.setState("ended");
    this.mic?.stop();
    this.stopRing?.();
    setTimeout(() => this.player?.close(), 5000);
  }

  cleanup() {
    this.stopRing?.();
    this.stopRing = null;
    this.mic?.stop();
    this.player?.close();
  }
}
