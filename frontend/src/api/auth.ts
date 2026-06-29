import { apiGet, apiPost, apiPut } from "./client";

export async function login(account: string, password: string): Promise<string> {
  const data = await apiPost("/api/auth/login", { account, password });
  return data.access_token;
}

export async function register(email: string, phone: string, password: string, nickname: string = ""): Promise<string> {
  const data = await apiPost("/api/auth/register", { email, phone, password, nickname });
  return data.access_token;
}

export async function getMe(): Promise<{ id: string; email: string; phone: string; nickname: string }> {
  return apiGet("/api/auth/me");
}

export async function updateNickname(nickname: string): Promise<any> {
  return apiPut("/api/auth/me", { nickname });
}
