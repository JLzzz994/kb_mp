import { http, TOKEN_KEY, USER_KEY, PERMS_KEY } from "./client";

export interface CurrentUserInfo {
  id: number;
  username: string;
  display_name: string;
  department_id: number;
  department_name: string;
  role_codes: string[];
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user_info: CurrentUserInfo;
  permissions: string[];
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const { data } = await http.post<LoginResponse>("/auth/login", { username, password });
  // 演示期按接口约定 §11 存 localStorage
  localStorage.setItem(TOKEN_KEY, data.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(data.user_info));
  localStorage.setItem(PERMS_KEY, JSON.stringify(data.permissions));
  return data;
}

export async function fetchMe(): Promise<{ user_info: CurrentUserInfo; permissions: string[] }> {
  const { data } = await http.get("/auth/me");
  return { user_info: data.user_info ?? data, permissions: data.permissions ?? [] };
}

export function logout(): void {
  // 服务端无状态，前端清 token 即可
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(PERMS_KEY);
}
