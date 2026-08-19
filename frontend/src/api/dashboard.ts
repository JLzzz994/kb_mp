import { http } from "./client";

export interface MetricsResponse {
  access_count: number;
  unique_users: number;
  unit_count: number;
  total_tokens: number;
  avg_response_time_ms: number;
  range_days: number;
}

export interface QuestionRankingItem {
  question: string;
  ask_count: number;
  last_asked_at: string;
}

export interface UnitRankingItem {
  unit_id: number;
  unit_code: string;
  title: string;
  access_count: number;
}

export interface TokenStatsBucket {
  bucket_date: string;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface ResponseTimeStatsBucket {
  bucket_date: string;
  avg_response_time_ms: number;
  p95_response_time_ms: number;
  sample_count: number;
}

export type StatsRange = "7d" | "30d" | "90d";

/** 后端实际契约：range 为整数天数（OpenAPI 实测，文档中的 "7d" 字符串与实现不符） */
const RANGE_DAYS: Record<StatsRange, number> = { "7d": 7, "30d": 30, "90d": 90 };

export async function getMetrics(range: StatsRange): Promise<MetricsResponse> {
  const { data } = await http.get<MetricsResponse>("/dashboard/metrics", {
    params: { range: RANGE_DAYS[range] },
  });
  return data;
}

export async function getQuestionRankings(rangeDays = 30): Promise<QuestionRankingItem[]> {
  const { data } = await http.get<QuestionRankingItem[]>("/dashboard/rankings/questions", {
    params: { range: rangeDays },
  });
  return data;
}

export async function getUnitRankings(rangeDays = 30): Promise<UnitRankingItem[]> {
  const { data } = await http.get<UnitRankingItem[]>("/dashboard/rankings/units", {
    params: { range: rangeDays },
  });
  return data;
}

export async function getTokenStats(rangeDays = 7): Promise<TokenStatsBucket[]> {
  const { data } = await http.get<TokenStatsBucket[]>("/dashboard/stats/tokens", {
    params: { range: rangeDays },
  });
  return data;
}

export async function getResponseTimeStats(rangeDays = 7): Promise<ResponseTimeStatsBucket[]> {
  const { data } = await http.get<ResponseTimeStatsBucket[]>("/dashboard/stats/response-time", {
    params: { range: rangeDays },
  });
  return data;
}
