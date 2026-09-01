import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Plus,
  Send,
  Trash2,
  Loader2,
  BookMarked,
  Lock,
  CircleAlert,
  Gauge,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  listSessions,
  createSession,
  deleteSession,
  chatStream,
  SseError,
  type SessionListItem,
  type CitationEventData,
  type UnauthorizedEventData,
} from "@/api/ai";
import { ApiError } from "@/api/client";
import { cn, formatMs } from "@/lib/utils";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: CitationEventData[];
  unauthorized?: UnauthorizedEventData["unit_ids"];
  usage?: { total_tokens: number; response_time_ms: number };
  streaming?: boolean;
}

type Phase = "idle" | "streaming" | "interrupted";

const QUESTION_MAX = 2000; // ChatStreamRequest: question 1–2000

export default function ChatPage() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionListItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [input, setInput] = useState(""); // interrupt 后保留输入框
  const [sendError, setSendError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const refreshSessions = useCallback(async () => {
    try {
      const list = await listSessions();
      setSessions(list);
      return list;
    } catch {
      return [];
    }
  }, []);

  useEffect(() => {
    void (async () => {
      const list = await refreshSessions();
      if (list.length > 0) setActiveId((cur) => cur ?? list[0].id);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const handleNewSession = async () => {
    try {
      const id = await createSession();
      setSessions((prev) => [
        { id, title: "新对话", updated_at: new Date().toISOString() },
        ...prev,
      ]);
      setActiveId(id);
      setMessages([]);
      setPhase("idle");
      setInput("");
    } catch (err) {
      setSendError(err instanceof ApiError ? `创建会话失败：${err.message}` : "创建会话失败");
    }
  };

  const handleDeleteSession = async (id: string) => {
    setConfirmDelete(null);
    try {
      await deleteSession(id);
      const list = await refreshSessions();
      if (activeId === id) {
        setActiveId(list[0]?.id ?? null);
        setMessages([]);
      }
    } catch {
      /* 保留在列表中，失败提示见全局 */
    }
  };

  const handleSend = async () => {
    const question = input.trim();
    if (!question || phase === "streaming" || !activeId) return;
    setSendError(null);
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setPhase("streaming");
    setMessages((prev) => [...prev, { role: "assistant", content: "", streaming: true }]);

    const controller = new AbortController();
    abortRef.current = controller;
    let terminated = false; // 是否收到过 final / interrupt / error 终止事件

    try {
      await chatStream(activeId, question, {
        signal: controller.signal,
        onEvent: (ev) => {
          if (ev.type === "final" || ev.type === "interrupt" || ev.type === "error") {
            terminated = true;
          }
          setMessages((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            switch (ev.type) {
              case "ready":
                break;
              case "progress":
                break;
              case "delta":
                if (last?.role === "assistant") {
                  next[next.length - 1] = { ...last, content: last.content + ev.text };
                }
                break;
              case "citation":
                if (last?.role === "assistant") {
                  next[next.length - 1] = {
                    ...last,
                    citations: [...(last.citations ?? []), ev.data],
                  };
                }
                break;
              case "unauthorized":
                if (last?.role === "assistant") {
                  next[next.length - 1] = {
                    ...last,
                    unauthorized: ev.data.unit_ids,
                  };
                }
                break;
              case "interrupt":
                // 召回为空/无权限：提示并保留输入框，等待用户补充（走 resume）
                next[next.length - 1] = {
                  role: "assistant",
                  content: "未找到与您的问题相关的产品知识。请补充产品版本、店铺/仓库、订单类型或异常现象，我将重新检索。",
                };
                break;
              case "final":
                next[next.length - 1] = {
                  role: "assistant",
                  content: ev.data.answer,
                  usage: {
                    total_tokens: ev.data.usage.total_tokens,
                    response_time_ms: ev.data.usage.response_time_ms,
                  },
                };
                break;
              case "error":
                next[next.length - 1] = {
                  role: "assistant",
                  content: `回答生成失败（${ev.error_code}）：${ev.detail}`,
                };
                break;
            }
            return next;
          });
          if (ev.type === "interrupt") setPhase("interrupted");
          if (ev.type === "final" || ev.type === "error") setPhase("idle");
          if (ev.type === "final") void refreshSessions();
        },
      });
      // 流正常结束但未收到终止事件（服务端异常关闭）→ 回到就绪态并恢复输入
      if (!terminated) {
        setPhase("idle");
        setInput(question);
      }
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last?.role === "assistant" && last.streaming) {
          next[next.length - 1] = {
            role: "assistant",
            content:
              err instanceof SseError || err instanceof ApiError
                ? `请求失败：${err.message}`
                : "网络中断，请重试。",
          };
        }
        return next;
      });
      setPhase("idle");
      // 出错时恢复用户输入，绝不清空
      setInput(question);
      if (err instanceof SseError || err instanceof ApiError) {
        setSendError(`请求失败：${err.message}`);
      }
    } finally {
      abortRef.current = null;
    }
  };

  const interruptHint = phase === "interrupted";

  return (
    <div className="animate-fade-up">
      <div className="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)_300px]">
        {/* 左栏：会话历史 */}
        <aside className="hidden lg:block">
          <Button className="mb-3 w-full" onClick={() => void handleNewSession()}>
            <Plus className="h-4 w-4" aria-hidden /> 新建会话
          </Button>
          <ScrollArea className="h-[calc(100vh-220px)] rounded-lg border border-boundary bg-card">
            <ul className="divide-y divide-boundary p-1">
              {sessions.length === 0 && (
                <li className="px-3 py-8 text-center text-[13px] text-secondarytext">暂无历史会话</li>
              )}
              {sessions.map((s) => (
                <li key={s.id}>
                  <button
                    onClick={() => setActiveId(s.id)}
                    className={cn(
                      "group flex w-full min-h-[44px] items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition",
                      activeId === s.id ? "bg-brand-soft text-ink" : "text-primarytext hover:bg-mist",
                    )}
                  >
                    <span className="min-w-0 flex-1 truncate">{s.title ?? "未命名会话"}</span>
                    <span
                      role="button"
                      tabIndex={0}
                      aria-label={`删除会话 ${s.title ?? s.id}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setConfirmDelete(s.id);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.stopPropagation();
                          setConfirmDelete(s.id);
                        }
                      }}
                      className="hidden h-8 w-8 items-center justify-center rounded text-secondarytext hover:bg-danger-soft hover:text-danger group-hover:flex"
                    >
                      <Trash2 className="h-4 w-4" aria-hidden />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </ScrollArea>
        </aside>

        {/* 中栏：对话主区（AI 工作台用 Deep Navy 主背景） */}
        <section className="flex min-h-[70vh] flex-col overflow-hidden rounded-lg border border-navy/20 bg-navy">
          <header className="flex items-center justify-between border-b border-white/10 px-5 py-3.5">
            <p className="font-display text-sm font-bold text-white">ERP/WMS 鉴权问答</p>
            <span className="code-text text-xs text-white/45">
              {phase === "streaming" ? "生成中…" : interruptHint ? "等待补充问题" : "就绪"}
            </span>
          </header>
          {/* 权限脉冲线：召回 → 鉴权 → 回答 */}
          <div className="permission-pulse-line mx-5 mt-1" aria-hidden />

          <ScrollArea className="thin-scrollbar flex-1 px-5 py-4">
            <div className="space-y-4">
              {messages.length === 0 && (
                <div className="py-16 text-center">
                  <p className="font-display text-lg font-bold text-white/90">基于您有权访问的 ERP/WMS 产品知识回答</p>
                  <p className="mt-2 text-sm text-white/50">
                    围绕订单、商品/SKU、库存、仓储、采购和售后检索；无权限内容不会进入回答。
                  </p>
                </div>
              )}
              {messages.map((m, i) => (
                <div key={i} className={cn("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                  <div
                    className={cn(
                      "max-w-[85%] rounded-xl px-4 py-3 text-sm leading-relaxed",
                      m.role === "user"
                        ? "bg-brand text-navy-deep"
                        : "bg-white/8 text-white/90 ring-1 ring-white/10",
                    )}
                  >
                    {m.content || (m.streaming ? "…" : "")}
                    {m.streaming && m.content === "" && (
                      <Loader2 className="h-4 w-4 animate-spin text-brand" aria-hidden />
                    )}
                    {m.usage && (
                      <p className="code-text mt-2 flex items-center gap-2 text-[11px] text-white/40">
                        <Gauge className="h-3 w-3" aria-hidden />
                        {m.usage.total_tokens} tokens · {formatMs(m.usage.response_time_ms)}
                      </p>
                    )}
                  </div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          </ScrollArea>

          {/* 输入区：interrupt 时保留输入并引导补充 */}
          <footer className="border-t border-white/10 p-4">
            {interruptHint && (
              <p className="mb-2 flex items-center gap-2 text-xs text-review" role="status">
                <CircleAlert className="h-3.5 w-3.5" aria-hidden />
                未找到相关知识 —— 补充说明后发送，将自动续接本轮问答。
              </p>
            )}
            {sendError && (
              <p className="mb-2 text-xs text-danger" role="alert">
                {sendError}
              </p>
            )}
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                void handleSend();
              }}
            >
              <Input
                value={input}
                maxLength={QUESTION_MAX}
                onChange={(e) => setInput(e.target.value)}
                placeholder={activeId ? "输入问题，如：WMS 库存同步异常怎么排查？" : "请先新建会话"}
                disabled={!activeId || phase === "streaming"}
                aria-label="问题输入"
                className="border-white/15 bg-white/10 text-white placeholder:text-white/35"
              />
              <Button type="submit" disabled={!input.trim() || phase === "streaming" || !activeId}>
                {phase === "streaming" ? (
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                ) : (
                  <Send className="h-4 w-4" aria-hidden />
                )}
                发送
              </Button>
            </form>
            <p className="mt-1.5 text-right text-[11px] text-white/35">
              {input.length}/{QUESTION_MAX}
            </p>
          </footer>
        </section>

        {/* 右栏：引用与鉴权结果 */}
        <aside className="space-y-4">
          <div className="rounded-lg border border-boundary bg-card p-4">
            <p className="flex items-center gap-2 font-display text-sm font-bold text-ink">
              <BookMarked className="h-4 w-4 text-brand" aria-hidden /> 产品知识引用
            </p>
            <div className="permission-pulse-line mt-3" aria-hidden />
            <ul className="mt-3 space-y-2">
              {messages.flatMap((m) => m.citations ?? []).length === 0 && (
                <li className="py-6 text-center text-[13px] text-secondarytext">
                  回答引用的知识单元将在此展示
                </li>
              )}
              {messages
                .flatMap((m) => m.citations ?? [])
                .map((c) => (
                  <li key={c.unit_id} className="rounded-md border border-boundary bg-mist/60 px-3 py-2.5">
                    <p className="truncate text-[13px] font-medium text-ink" title={c.title}>
                      {c.title}
                    </p>
                    <p className="code-text mt-0.5 text-[11px] text-secondarytext">
                      #{c.unit_id} · 相似度 {(c.score * 100).toFixed(0)}%
                    </p>
                  </li>
                ))}
            </ul>
          </div>

          <div className="rounded-lg border border-review/40 bg-review-soft p-4">
            <p className="flex items-center gap-2 font-display text-sm font-bold text-ink">
              <Lock className="h-4 w-4 text-review" aria-hidden /> 无权限单元
            </p>
            <ul className="mt-3 space-y-2">
              {messages.flatMap((m) => m.unauthorized ?? []).length === 0 ? (
                <li className="py-4 text-center text-[13px] text-secondarytext">
                  本轮召回内容均在您的权限范围内
                </li>
              ) : (
                messages
                  .flatMap((m) => m.unauthorized ?? [])
                  .map((u) => (
                    <li key={u.id} className="rounded-md bg-card px-3 py-2.5">
                      {/* 无权限只展示编号与分数，不泄露正文 */}
                      <p className="code-text text-[12px] text-ink">知识单元 #{u.id}</p>
                      <p className="mt-0.5 text-[11px] text-secondarytext">
                        {u.score != null ? `相似度 ${(u.score * 100).toFixed(0)}% · ` : ""}
                        无访问权限，正文已隐藏
                      </p>
                      <button
                        onClick={() => navigate("/knowledge/units")}
                        className="mt-1 text-[12px] font-medium text-review underline-offset-2 hover:underline"
                      >
                        申请权限 →
                      </button>
                    </li>
                  ))
              )}
            </ul>
          </div>
        </aside>
      </div>

      {/* 删除会话二次确认 */}
      <Dialog open={Boolean(confirmDelete)} onOpenChange={(o) => !o && setConfirmDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除会话</DialogTitle>
            <DialogDescription>删除后对话历史不可恢复。</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(null)}>
              取消
            </Button>
            <Button variant="destructive" onClick={() => confirmDelete && void handleDeleteSession(confirmDelete)}>
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
