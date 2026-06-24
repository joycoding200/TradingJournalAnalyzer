const BASE_URL = "";

function getToken(): string | null {
  return localStorage.getItem("token");
}

function onAuthExpired() {
  localStorage.removeItem("token");
  // Avoid redirect loop on login/register pages
  const path = window.location.pathname;
  if (path !== "/login" && path !== "/register" && path !== "/") {
    window.location.href = "/login?expired=1";
  }
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const isFormData = options.body instanceof FormData;
  if (!isFormData && options.body && typeof options.body === "string") {
    headers["Content-Type"] = "application/json";
  }
  const resp = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  if (resp.status === 401) {
    onAuthExpired();
  }
  return resp;
}

export async function apiPost(path: string, body?: unknown): Promise<any> {
  const resp = await apiFetch(path, {
    method: "POST",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return resp.json();
}

export async function apiGet(path: string): Promise<any> {
  const resp = await apiFetch(path);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return resp.json();
}

export async function apiUpload(path: string, formData: FormData): Promise<any> {
  const token = getToken();
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (resp.status === 401) {
    onAuthExpired();
    throw new Error("登录已过期，请重新登录");
  }
  if (!resp.ok) throw new Error("Upload failed");
  return resp.json();
}

export async function apiPut(path: string, body?: unknown): Promise<any> {
  const resp = await apiFetch(path, {
    method: "PUT",
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return resp.json();
}

export async function apiDelete(path: string): Promise<any> {
  const resp = await apiFetch(path, { method: "DELETE" });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || "Request failed");
  }
  return resp.json();
}
