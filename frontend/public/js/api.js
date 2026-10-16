// Backend access: REST (X-Client-Id header), WebSocket URLs and the anonymous client id.

const DEFAULT_BASE = (window.SW_CONFIG && window.SW_CONFIG.backendUrl) || "";

function resolveBase() {
  // A ?api=<url> override is honoured only on localhost, so a crafted link cannot point the app at another server.
  const local = ["localhost", "127.0.0.1"].includes(location.hostname);
  if (local) {
    const fromQuery = new URLSearchParams(location.search).get("api");
    if (fromQuery) localStorage.setItem("sw_api", fromQuery);
    const stored = localStorage.getItem("sw_api");
    if (stored) return stored.replace(/\/$/, "");
  }
  return DEFAULT_BASE.replace(/\/$/, "");
}

export const BASE = resolveBase();
export const WS_BASE = BASE.replace(/^http/, "ws");

export function clientId() {
  let id = localStorage.getItem("sw_client_id");
  if (!id || !/^[A-Za-z0-9_-]{16,64}$/.test(id)) {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    id = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    localStorage.setItem("sw_client_id", id);
  }
  return id;
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, { method = "GET", body, raw = false } = {}) {
  let response;
  try {
    response = await fetch(BASE + path, {
      method,
      headers: { "X-Client-Id": clientId(), ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection and try again.", 0);
  }
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") detail = data.detail;
      else if (Array.isArray(data.detail) && data.detail[0]?.msg) detail = data.detail[0].msg;
    } catch {
      /* keep default */
    }
    throw new ApiError(detail, response.status);
  }
  return raw ? response : response.json();
}

export const api = {
  health: () => fetch(BASE + "/health").then((r) => r.json()),
  config: () => request("/api/config"),
  calls: () => request("/api/calls"),
  call: (id) => request(`/api/calls/${encodeURIComponent(id)}`),
  evidenceBlob: async (id) => (await request(`/api/calls/${encodeURIComponent(id)}/evidence`, { raw: true })).blob(),
  recordingBlob: async (path) => {
    const response = await fetch(BASE + path);
    if (!response.ok) throw new ApiError("Recording is not available.", response.status);
    return response.blob();
  },
  recordingDownloadUrl: (path) => `${BASE}${path}${path.includes("?") ? "&" : "?"}download=1`,
  strains: () => request("/api/strains"),
  createDrill: (payload) => request("/api/drills", { method: "POST", body: payload }),
  drills: () => request("/api/drills"),
  drill: (id) => request(`/api/drills/${encodeURIComponent(id)}`),
  banks: () => request("/api/banks"),
  watchlist: () => request("/api/watchlist"),
  bankReports: (code) => request(`/api/banks/${encodeURIComponent(code)}/reports`),
  bankDecision: (code, reportId, decision) =>
    request(`/api/banks/${encodeURIComponent(code)}/reports/${encodeURIComponent(reportId)}/decision`, { method: "POST", body: { decision } }),
  invite: (id, key) => request(`/api/drills/${encodeURIComponent(id)}/invite?k=${encodeURIComponent(key)}`),
};

export function wsUrl(path) {
  return `${WS_BASE}${path}`;
}
