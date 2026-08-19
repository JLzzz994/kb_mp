/**
 * axios 统一封装（接口约定文档 §11）
 * - Token 存 localStorage（演示期），拦截器自动注入 Authorization
 * - 401 响应：清 token + 跳登录
 * - 错误体统一为 { detail, error_code, request_id }
 */
import axios, { AxiosError } from "axios";

export const TOKEN_KEY = "kb_access_token";
export const USER_KEY = "kb_user_info";
export const PERMS_KEY = "kb_permissions";

export interface ApiErrorBody {
  detail?: string;
  error_code?: string;
  request_id?: string;
}

export class ApiError extends Error {
  status: number;
  errorCode?: string;
  requestId?: string;
  /** 422 时 Pydantic 错误的 field 提示 */
  fields?: Record<string, string>;

  constructor(status: number, body: ApiErrorBody, fields?: Record<string, string>) {
    super(body.detail ?? `请求失败（HTTP ${status}）`);
    this.name = "ApiError";
    this.status = status;
    this.errorCode = body.error_code;
    this.requestId = body.request_id;
    this.fields = fields;
  }
}

export const http = axios.create({
  baseURL: "/api/v1",
  timeout: 30_000,
});

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // 链路追踪（可选）
  config.headers["X-Request-Id"] = crypto.randomUUID?.() ?? undefined;
  return config;
});

http.interceptors.response.use(
  (resp) => resp,
  (error: AxiosError<ApiErrorBody>) => {
    const status = error.response?.status ?? 0;
    if (status === 401) {
      // Token 无效/过期：清凭证回登录页（保留当前路径，便于登录后回跳）
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      localStorage.removeItem(PERMS_KEY);
      if (!window.location.pathname.startsWith("/login")) {
        const redirect = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.assign(`/login?redirect=${redirect}`);
      }
    }
    let fields: Record<string, string> | undefined;
    if (status === 422 && Array.isArray(error.response?.data)) {
      // FastAPI 校验错误数组 → field 级提示
      fields = {};
      for (const item of error.response!.data as Array<{ loc: string[]; msg: string }>) {
        const key = item.loc?.filter((l) => l !== "body").join(".");
        if (key) fields[key] = item.msg;
      }
    }
    return Promise.reject(new ApiError(status, error.response?.data ?? {}, fields));
  },
);

/** 列表分页响应（Page[T]） */
export interface PageData<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

/** 通用列表 query 参数 */
export interface ListQuery {
  page?: number;
  page_size?: number;
  keyword?: string;
  status?: string;
  category?: string;
  sort?: string;
}
