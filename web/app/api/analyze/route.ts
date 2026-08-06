import { NextResponse } from "next/server";
import { API_BASE } from "@/lib/api";

/**
 * Thin proxy to the Python service. Keeps the browser same-origin (no CORS
 * config on Flask) and keeps the API host out of the client bundle.
 */
export async function POST(request: Request) {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  try {
    const response = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      cache: "no-store",
    });
    const body = await response.json();
    return NextResponse.json(body, { status: response.status });
  } catch {
    return NextResponse.json(
      { error: "Can't reach the analysis service. Start it with `python app.py`." },
      { status: 503 },
    );
  }
}
