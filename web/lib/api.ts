import type { ModelInfo, ProfileResponse } from "./types";

/**
 * The Python service owns the model; this app only renders what it returns.
 * Requests go out from the server so the browser never talks to Flask
 * directly - no CORS setup, no API host leaking into the client bundle.
 */
function resolveApiBase(): string {
  const explicit = process.env.TOXICITY_API_URL?.trim();
  if (explicit) return normalize(explicit);

  // Platforms that wire services together hand over a bare hostname rather
  // than a URL. Two shapes turn up: a public domain (`api.example.com`) which
  // is served over TLS, and a private-network name (`x-toxicity-api`) which is
  // plain HTTP on the service's own port, never 443.
  const host = process.env.TOXICITY_API_HOST?.trim();
  if (host) {
    if (/^https?:\/\//i.test(host)) return normalize(host);

    const port = process.env.TOXICITY_API_PORT?.trim();
    if (host.includes(".")) return normalize(`https://${host}${port ? `:${port}` : ""}`);
    return normalize(`http://${host}:${port || "10000"}`);
  }

  return "http://127.0.0.1:5000";
}

function normalize(url: string) {
  return url.replace(/\/+$/, "");
}

export const API_BASE = resolveApiBase();

// A free-plan service that has spun down answers 502/503 from the platform's
// router for a few seconds while it boots, and a cold start that has to load
// the model is slow enough to outlast the default fetch timeout.
const REQUEST_TIMEOUT_MS = 120_000;
const WAKE_RETRIES = 2;
const WAKE_RETRY_DELAY_MS = 3_000;
const WAKE_STATUSES = new Set([502, 503, 504]);

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/**
 * Keyed off where the API actually is, not off NODE_ENV: a deployed frontend
 * pointed at a loopback address is exactly the misconfiguration worth naming,
 * and NODE_ENV was reporting it as a "start python app.py" problem to users who
 * have no local process to start.
 */
export function unreachableMessage() {
  const loopback = /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:|\/|$)/i.test(API_BASE);
  return loopback
    ? `Can't reach the analysis service at ${API_BASE}. Locally, start it with \`python app.py\`; if this is a deployment, set TOXICITY_API_URL to the API's public URL.`
    : `Can't reach the analysis service at ${API_BASE}. It may still be starting up — try again in a moment.`;
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * One request to the Python service, retried while the platform reports the
 * service as still coming up. Network failures and timeouts surface as the
 * same "unreachable" error the pages render.
 */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = `${API_BASE}${path}`;

  for (let attempt = 0; ; attempt++) {
    let response: Response;
    try {
      response = await fetch(url, {
        ...init,
        cache: "no-store",
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
    } catch (error) {
      // A refused connection means nothing is listening at all; retrying only
      // stalls the page. A timeout or a dropped connection can be a service
      // still waking up, so those get another go.
      const refused =
        (error as { cause?: { code?: string } })?.cause?.code === "ECONNREFUSED";
      if (!refused && attempt < WAKE_RETRIES) {
        await sleep(WAKE_RETRY_DELAY_MS);
        continue;
      }
      throw new ApiError(unreachableMessage(), 503);
    }

    // A 502 from the platform's router means "still booting"; a 502 from the
    // Python service itself is a real answer (it uses that status when X
    // refuses it). Only the former is worth waiting on — retrying the latter
    // sat on a genuine error message for six seconds before showing it.
    const fromPlatform = !(response.headers.get("content-type") || "").includes(
      "application/json",
    );
    if (WAKE_STATUSES.has(response.status) && fromPlatform && attempt < WAKE_RETRIES) {
      await sleep(WAKE_RETRY_DELAY_MS);
      continue;
    }
    return response;
  }
}

async function readError(response: Response, fallback: string) {
  try {
    const body = await response.json();
    return typeof body?.error === "string" ? body.error : fallback;
  } catch {
    return fallback;
  }
}

export async function fetchProfile(
  username: string,
  posts: number,
): Promise<ProfileResponse> {
  const response = await apiFetch(
    `/api/profile/${encodeURIComponent(username)}?posts=${posts}`,
  );

  if (!response.ok) {
    throw new ApiError(
      await readError(response, `Analysis failed (HTTP ${response.status})`),
      response.status,
    );
  }
  return response.json();
}

export async function fetchModelInfo(): Promise<ModelInfo | null> {
  try {
    // Deliberately uncached: retraining changes these numbers, and a page
    // baked while the service was down would advertise it as offline.
    const response = await apiFetch("/api/model");
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}
