import { NextResponse } from "next/server";
import { API_BASE } from "@/lib/api";

/**
 * Forwards every `/api/*` request to the Python service.
 *
 * This is what makes the whole app answer on one port: the browser only ever
 * talks to this origin, and the Python service can sit on a private port (or a
 * different host entirely) without CORS configuration.
 *
 * It is a route handler rather than a `next.config` rewrite on purpose —
 * rewrites are baked into the build, while this reads the API location at
 * request time, so the same build works wherever the API happens to be.
 */

const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "host",
]);

async function proxy(request: Request, path: string[]) {
  const suffix = path.map(encodeURIComponent).join("/");
  const query = new URL(request.url).search;
  const target = `${API_BASE}/api/${suffix}${query}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });

  const method = request.method.toUpperCase();
  const body =
    method === "GET" || method === "HEAD" ? undefined : await request.arrayBuffer();

  let response: Response;
  try {
    response = await fetch(target, {
      method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return NextResponse.json(
      {
        error:
          "Can't reach the analysis service. Start it with `python app.py`.",
      },
      { status: 503 },
    );
  }

  const outHeaders = new Headers();
  response.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase()) && key.toLowerCase() !== "content-encoding") {
      outHeaders.set(key, value);
    }
  });

  return new NextResponse(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: outHeaders,
  });
}

type Context = { params: Promise<{ path: string[] }> };

export async function GET(request: Request, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function POST(request: Request, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function PUT(request: Request, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function PATCH(request: Request, context: Context) {
  return proxy(request, (await context.params).path);
}

export async function DELETE(request: Request, context: Context) {
  return proxy(request, (await context.params).path);
}
