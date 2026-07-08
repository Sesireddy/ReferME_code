import { storage } from "@/src/utils/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL || "";

const TOKEN_KEY = "referme_token";
const USER_KEY = "referme_user";

export type UserShape = {
  id: string;
  email: string;
  role: "student" | "professional" | "employer" | "admin";
  name: string;
  credits: number;
  free_uses_left: number;
  total_deposits: number;
  is_email_verified: boolean;
  profile_complete: boolean;
};

export async function setSession(token: string, user: UserShape) {
  await storage.secureSet(TOKEN_KEY, token);
  await storage.setItem(USER_KEY, JSON.stringify(user));
}

export async function getToken(): Promise<string | null> {
  return (await storage.secureGet(TOKEN_KEY, "")) || null;
}

export async function getUser(): Promise<UserShape | null> {
  const raw = await storage.getItem(USER_KEY, "");
  if (!raw) return null;
  try {
    return JSON.parse(raw as string) as UserShape;
  } catch {
    return null;
  }
}

export async function clearSession() {
  await storage.secureRemove(TOKEN_KEY);
  await storage.removeItem(USER_KEY);
}

export async function api<T = any>(
  path: string,
  opts: { method?: string; body?: any; auth?: boolean } = {}
): Promise<T> {
  const { method = "GET", body, auth = true } = opts;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) {
    const t = await getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
  const res = await fetch(`${BASE}/api${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    const rawDetail = data && (data.detail ?? data.message);
    const msg = typeof rawDetail === "string"
      ? rawDetail
      : (rawDetail && typeof rawDetail === "object" && typeof rawDetail.message === "string")
          ? rawDetail.message
          : (rawDetail ? JSON.stringify(rawDetail) : `HTTP ${res.status}`);
    const err = new Error(msg) as Error & { status?: number; detail?: any; payload?: any };
    err.status = res.status;
    err.detail = rawDetail;  // structured server-side detail (may be a string, object, or list)
    err.payload = data;      // full raw JSON response body for advanced handlers
    throw err;
  }
  return data as T;
}
