/**
 * AI 对话：会话 CRUD + SSE 流式问答（接口约定文档 §6）
 * EventSource 不支持自定义 header，统一用 fetch + ReadableStream。
 */
import { http, TOKEN_KEY } from "./client";
import { generateUuid } from "@/lib/utils";

export interface SessionListItem {
  id: string;
  title: string | null;
  updated_at: string;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  citations?: Array<{ unit_id: number; title: string; score: number }>;
  created_at?: string;
}

export interface PendingTurn {
  question: string;
  reason: "no_recall" | "no_recall_with_permission" | "low_confidence";
  recalled_unit_ids: number[];
  authorized_unit_ids: number[];
  created_at: string;
  status: "pending" | "resumed" | "abandoned";
}

export interface ChatSessionDetail {
  id: string;
  title: string | null;
  history_json: {
    turns: ChatTurn[];
    slots: Record<string, unknown>;
    pending_turn: PendingTurn | null;
  };
  created_at: string;
  updated_at: string;
}

/** 创建会话：id 由客户端生成 UUID */
export async function createSession(title?: string): Promise<string> {
  const id = generateUuid();
  await http.post("/ai/sessions", { id, title: title ?? null });
  return id;
}

export async function listSessions(): Promise<SessionListItem[]> {
  const { data } = await http.get<SessionListItem[]>("/ai/sessions");
  return Array.isArray(data) ? data : (data as { items: SessionListItem[] }).items;
}

export async function getSession(id: string): Promise<ChatSessionDetail> {
  const { data } = await http.get<ChatSessionDetail>(`/ai/sessions/${id}`);
  return data;
}

export async function updateSessionTitle(id: string, title: string): Promise<void> {
  await http.patch(`/ai/sessions/${id}`, { title });
}

export async function deleteSession(id: string): Promise<void> {
  await http.delete(`/ai/sessions/${id}`);
}

/* ---------------- SSE 事件 ---------------- */

export interface CitationEventData {
  unit_id: number;
  title: string;
  score: number;
}

export interface UnauthorizedUnit {
  id: number;
  /** 后端实测仅下发 int 数组（文档承诺对象数组带 score，实现未兑现），score 可为空 */
  score: number | null;
}

export interface UnauthorizedEventData {
  unit_ids: UnauthorizedUnit[];
}

export interface InterruptEventData {
  reason: "no_recall" | "no_recall_with_permission" | "low_confidence";
  session_id: string;
}

export interface FinalEventData {
  answer: string;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    response_time_ms: number;
  };
}

export type ChatSseEvent =
  | { type: "ready"; session_id: string }
  | { type: "progress"; step: string; progress?: number }
  | { type: "delta"; text: string }
  | { type: "citation"; data: CitationEventData }
  | { type: "unauthorized"; data: UnauthorizedEventData }
  | { type: "interrupt"; data: InterruptEventData }
  | { type: "final"; data: FinalEventData }
  | { type: "error"; error_code: string; detail: string };

export class SseError extends Error {
  errorCode: string;
  constructor(errorCode: string, detail: string) {
    super(detail);
    this.name = "SseError";
    this.errorCode = errorCode;
  }
}

/** 解析 SSE 文本块（event: xxx / data: {...}），跨 chunk 用 buffer 续接 */
function parseSseChunk(buffer: string): { events: ChatSseEvent[]; rest: string } {
  const events: ChatSseEvent[] = [];
  let rest = buffer;
  const separator = "\n\n";
  let idx = rest.indexOf(separator);
  while (idx !== -1) {
    const block = rest.slice(0, idx);
    rest = rest.slice(idx + separator.length);
    let eventName = "message";
    let dataRaw = "";
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataRaw += line.slice(5).trim();
    }
    if (eventName === "message" && !dataRaw) {
      idx = rest.indexOf(separator);
      continue;
    }
    events.push(buildEvent(eventName, dataRaw));
    idx = rest.indexOf(separator);
  }
  return { events, rest };
}

function buildEvent(name: string, raw: string): ChatSseEvent {
  let data: Record<string, unknown> = {};
  try {
    data = raw ? JSON.parse(raw) : {};
  } catch {
    data = { text: raw };
  }
  switch (name) {
    case "ready":
      return { type: "ready", session_id: String(data.session_id ?? "") };
    case "progress":
      // 后端实测只下发 {"stage": "xxx"}，文档承诺 {step, progress}，两者兼容
      return {
        type: "progress",
        step: String(data.step ?? data.stage ?? ""),
        progress: data.progress != null ? Number(data.progress) : undefined,
      };
    case "delta":
      return { type: "delta", text: String(data.text ?? "") };
    case "citation":
      return { type: "citation", data: data as unknown as CitationEventData };
    case "unauthorized": {
      // 后端实测 unit_ids 为 int 数组（文档承诺对象数组带 score），统一规整
      const raw = (data as { unit_ids?: unknown[] }).unit_ids ?? [];
      const normalized: UnauthorizedUnit[] = raw.map((u) =>
        typeof u === "number"
          ? { id: u, score: null }
          : { id: Number((u as { id?: number }).id ?? 0), score: (u as { score?: number }).score ?? null },
      );
      return { type: "unauthorized", data: { unit_ids: normalized } };
    }
    case "interrupt":
      return { type: "interrupt", data: data as unknown as InterruptEventData };
    case "final":
      return { type: "final", data: data as unknown as FinalEventData };
    case "error":
      return { type: "error", error_code: String(data.error_code ?? "unknown"), detail: String(data.detail ?? "") };
    default:
      return { type: "delta", text: "" };
  }
}

export interface StreamHandlers {
  onEvent: (event: ChatSseEvent) => void;
  signal?: AbortSignal;
}

/**
 * 流式问答 / 续接。
 * 客户端无需区分 stream 与 resume：若 pending_turn 存在服务端自动续接（接口约定 §7.4）。
 * 统一调用 /ai/chat/stream；interrupt 后用户补充提问仍走本函数。
 */
export async function chatStream(
  sessionId: string,
  question: string,
  handlers: StreamHandlers,
): Promise<void> {
  const token = localStorage.getItem(TOKEN_KEY);
  const resp = await fetch("/api/v1/ai/chat/stream", {
    method: "POST",
    headers: {
      Authorization: token ? `Bearer ${token}` : "",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ session_id: sessionId, question }),
    signal: handlers.signal,
  });

  if (!resp.ok || !resp.body) {
    // HTTP 阶段错误走通用错误体 { detail, error_code }
    let detail = `请求失败（HTTP ${resp.status}）`;
    let errorCode = "http_error";
    try {
      const body = await resp.json();
      detail = body.detail ?? detail;
      errorCode = body.error_code ?? errorCode;
    } catch {
      /* 忽略解析失败 */
    }
    throw new SseError(errorCode, detail);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const { events, rest } = parseSseChunk(buffer);
      buffer = rest;
      for (const ev of events) handlers.onEvent(ev);
    }
    // flush 残余
    if (buffer.trim()) {
      const { events } = parseSseChunk(buffer + "\n\n");
      for (const ev of events) handlers.onEvent(ev);
    }
  } finally {
    reader.releaseLock();
  }
}
