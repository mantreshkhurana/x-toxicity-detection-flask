import type { ModelInfo, ProfileResponse } from "./types";

/**
 * The Python service owns the model; this app only renders what it returns.
 * Requests go out from the server so the browser never talks to Flask
 * directly - no CORS setup, no API host leaking into the client bundle.
 */
export const API_BASE =
  process.env.TOXICITY_API_URL?.replace(/\/$/, "") ?? "http://127.0.0.1:5000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
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
  const url = `${API_BASE}/api/profile/${encodeURIComponent(username)}?posts=${posts}`;

  let response: Response;
  try {
    response = await fetch(url, { cache: "no-store" });
  } catch {
    throw new ApiError(
      "Can't reach the analysis service. Start it with `python app.py`.",
      503,
    );
  }

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
    const response = await fetch(`${API_BASE}/api/model`, { cache: "no-store" });
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}
