export type AuthResult = { authenticated: boolean; expires_in: number };
export type Project = { id: string; name: string; description: string; repository_url: string | null; created_at: string; updated_at: string };
export type Profile = { id: string; email: string; full_name: string; created_at: string };

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...options, headers, credentials: "same-origin", cache: "no-store" });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const detail = typeof data?.error?.message === "string" ? data.error.message : typeof data?.detail === "string" ? data.detail : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

