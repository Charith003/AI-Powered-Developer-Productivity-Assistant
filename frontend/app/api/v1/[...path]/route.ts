import { NextRequest, NextResponse } from "next/server";

type TokenPayload = { access_token: string; refresh_token: string; expires_in: number };
const apiOrigin = process.env.API_URL ?? "http://localhost:8000";
const cookieOptions = { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax" as const, path: "/" };
const refreshableExclusions = new Set(["login", "register", "logout", "refresh"]);
type RouteContext = { params: Promise<{ path: string[] }> };

function attachTokens(response: NextResponse, tokens: TokenPayload) {
  response.cookies.set("devpilot_access", tokens.access_token, { ...cookieOptions, maxAge: tokens.expires_in });
  response.cookies.set("devpilot_refresh", tokens.refresh_token, cookieOptions);
  return response;
}
function clearTokens(response: NextResponse) {
  response.cookies.set("devpilot_access", "", { ...cookieOptions, maxAge: 0 });
  response.cookies.set("devpilot_refresh", "", { ...cookieOptions, maxAge: 0 });
  return response;
}
async function refreshTokens(refreshToken: string): Promise<TokenPayload | null> {
  const response = await fetch(`${apiOrigin}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
    cache: "no-store",
  });
  return response.ok ? ((await response.json()) as TokenPayload) : null;
}
async function handler(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const upstreamPath = `/api/v1/${path.map(encodeURIComponent).join("/")}`;
  const action = path[0] === "auth" ? path[1] : undefined;
  const mutating = !["GET", "HEAD", "OPTIONS"].includes(request.method);
  const origin = request.headers.get("origin");
  if (mutating && origin && origin !== request.nextUrl.origin) {
    return NextResponse.json({ detail: "Cross-origin request rejected" }, { status: 403 });
  }
  const refresh = request.cookies.get("devpilot_refresh")?.value;
  const access = request.cookies.get("devpilot_access")?.value;
  const body = ["logout", "refresh"].includes(action ?? "") && refresh
    ? JSON.stringify({ refresh_token: refresh })
    : ["GET", "HEAD"].includes(request.method) ? undefined : await request.text();
  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("Content-Type", contentType);
  if (["logout", "refresh"].includes(action ?? "") && refresh) headers.set("Content-Type", "application/json");
  headers.set("Accept", "application/json");
  if (access && !["login", "register", "refresh"].includes(action ?? "")) {
    headers.set("Authorization", `Bearer ${access}`);
  }
  const send = () => fetch(`${apiOrigin}${upstreamPath}${request.nextUrl.search}`, {
    method: request.method, headers, body, cache: "no-store",
  });
  let upstream: Response;
  try { upstream = await send(); }
  catch { return NextResponse.json({ detail: "The DevPilot API is unavailable" }, { status: 502 }); }

  let rotated: TokenPayload | null = null;
  if (upstream.status === 401 && refresh && !refreshableExclusions.has(action ?? "")) {
    rotated = await refreshTokens(refresh);
    if (rotated) {
      headers.set("Authorization", `Bearer ${rotated.access_token}`);
      upstream = await send();
    }
  }
  if ((action === "login" || action === "register") && upstream.ok) {
    const tokens = (await upstream.json()) as TokenPayload;
    return attachTokens(NextResponse.json({ authenticated: true, expires_in: tokens.expires_in }, { status: upstream.status }), tokens);
  }
  if (action === "logout") return clearTokens(new NextResponse(null, { status: upstream.status }));
  if (action === "refresh" && upstream.ok) {
    const tokens = (await upstream.json()) as TokenPayload;
    return attachTokens(NextResponse.json({ authenticated: true, expires_in: tokens.expires_in }, { status: upstream.status }), tokens);
  }
  const responseBody = await upstream.arrayBuffer();
  const response = new NextResponse(responseBody.byteLength ? responseBody : null, {
    status: upstream.status,
    headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
  });
  if (rotated) attachTokens(response, rotated);
  else if (upstream.status === 401 && refresh) clearTokens(response);
  return response;
}
export { handler as GET, handler as POST, handler as PUT, handler as PATCH, handler as DELETE };


