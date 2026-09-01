<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import {
  BookMarked,
  CircleAlert,
  Gauge,
  LoaderCircle,
  Lock,
  Plus,
  Send,
  Trash2,
} from "lucide-vue-next";

import {
  chatStream,
  createSession,
  deleteSession,
  getSession,
  listSessions,
  SseError,
  type CitationEventData,
  type SessionListItem,
  type UnauthorizedEventData,
} from "@/api/ai";
import { ApiError } from "@/api/client";
import { formatMs } from "@/lib/utils";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: CitationEventData[];
  unauthorized?: UnauthorizedEventData["unit_ids"];
  usage?: { total_tokens: number; response_time_ms: number };
  streaming?: boolean;
}

type Phase = "idle" | "streaming" | "interrupted";

const router = useRouter();
const sessions = ref<SessionListItem[]>([]);
const activeId = ref<string | null>(null);
const messages = ref<ChatMessage[]>([]);
const phase = ref<Phase>("idle");
const input = ref("");
const sendError = ref<string | null>(null);
const bottom = ref<HTMLDivElement | null>(null);
const questionMax = 2000;

const citations = computed(() => messages.value.flatMap((message) => message.citations ?? []));
const unauthorized = computed(() =>
  messages.value.flatMap((message) => message.unauthorized ?? []),
);

async function scrollBottom() {
  await nextTick();
  bottom.value?.scrollIntoView({ behavior: "smooth", block: "end" });
}

async function refreshSessions(): Promise<SessionListItem[]> {
  try {
    sessions.value = await listSessions();
    return sessions.value;
  } catch {
    return [];
  }
}

async function selectSession(id: string) {
  activeId.value = id;
  sendError.value = null;
  try {
    const session = await getSession(id);
    messages.value = (session.history_json?.turns ?? []).map((turn) => ({
      role: turn.role,
      content: turn.content,
    }));
    phase.value = session.history_json?.pending_turn ? "interrupted" : "idle";
    await scrollBottom();
  } catch {
    messages.value = [];
  }
}

async function newSession() {
  try {
    const id = await createSession();
    sessions.value = [
      { id, title: "新对话", updated_at: new Date().toISOString() },
      ...sessions.value,
    ];
    activeId.value = id;
    messages.value = [];
    phase.value = "idle";
    input.value = "";
  } catch (error) {
    sendError.value = error instanceof ApiError ? `创建会话失败：${error.message}` : "创建会话失败";
  }
}

async function removeSession(id: string) {
  if (!window.confirm("确认删除该会话？删除后历史不可恢复。")) return;
  try {
    await deleteSession(id);
    const list = await refreshSessions();
    if (activeId.value === id) {
      if (list[0]) await selectSession(list[0].id);
      else {
        activeId.value = null;
        messages.value = [];
      }
    }
  } catch {
    sendError.value = "删除会话失败";
  }
}

function updateLast(mutator: (last: ChatMessage) => ChatMessage) {
  const index = messages.value.length - 1;
  if (index < 0) return;
  const last = messages.value[index];
  if (last?.role !== "assistant") return;
  messages.value[index] = mutator(last);
  void scrollBottom();
}

async function send() {
  const question = input.value.trim();
  if (!question || phase.value === "streaming" || !activeId.value) return;

  sendError.value = null;
  input.value = "";
  messages.value.push({ role: "user", content: question });
  messages.value.push({ role: "assistant", content: "", streaming: true });
  phase.value = "streaming";
  await scrollBottom();

  const controller = new AbortController();
  let terminated = false;

  try {
    await chatStream(activeId.value, question, {
      signal: controller.signal,
      onEvent: (event) => {
        if (["final", "interrupt", "error"].includes(event.type)) terminated = true;

        if (event.type === "delta") {
          updateLast((last) => ({ ...last, content: last.content + event.text }));
        } else if (event.type === "citation") {
          updateLast((last) => ({
            ...last,
            citations: [...(last.citations ?? []), event.data],
          }));
        } else if (event.type === "unauthorized") {
          updateLast((last) => ({ ...last, unauthorized: event.data.unit_ids }));
        } else if (event.type === "interrupt") {
          updateLast(() => ({
            role: "assistant",
            content:
              "未找到与您的问题相关的产品知识。请补充产品版本、店铺/仓库、订单类型或异常现象，我将重新检索。",
          }));
          phase.value = "interrupted";
        } else if (event.type === "final") {
          updateLast((last) => ({
            role: "assistant",
            content: event.data.answer,
            citations: last.citations,
            unauthorized: last.unauthorized,
            usage: {
              total_tokens: event.data.usage.total_tokens,
              response_time_ms: event.data.usage.response_time_ms,
            },
          }));
          phase.value = "idle";
          void refreshSessions();
        } else if (event.type === "error") {
          updateLast(() => ({
            role: "assistant",
            content: `回答生成失败（${event.error_code}）：${event.detail}`,
          }));
          phase.value = "idle";
        }
      },
    });

    if (!terminated) {
      phase.value = "idle";
      input.value = question;
    }
  } catch (error) {
    updateLast((last) => ({
      ...last,
      streaming: false,
      content:
        error instanceof SseError || error instanceof ApiError
          ? `请求失败：${error.message}`
          : "网络中断，请重试。",
    }));
    phase.value = "idle";
    input.value = question;
    sendError.value =
      error instanceof SseError || error instanceof ApiError
        ? `请求失败：${error.message}`
        : "网络中断，请重试。";
  }
}

onMounted(async () => {
  const list = await refreshSessions();
  if (list[0]) await selectSession(list[0].id);
});
</script>

<template>
  <div class="animate-fade-up">
    <div class="grid gap-4 lg:grid-cols-[240px_minmax(0,1fr)_300px]">
      <aside class="hidden lg:block">
        <button class="mb-3 flex h-10 w-full items-center justify-center gap-2 rounded-md bg-brand text-sm font-bold text-navy-deep" @click="newSession">
          <Plus class="h-4 w-4" />新建会话
        </button>
        <div class="thin-scrollbar h-[calc(100vh-220px)] overflow-y-auto rounded-lg border border-boundary bg-card p-1">
          <p v-if="!sessions.length" class="px-3 py-8 text-center text-[13px] text-secondarytext">暂无历史会话</p>
          <button
            v-for="session in sessions"
            :key="session.id"
            class="group flex min-h-[44px] w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition"
            :class="activeId === session.id ? 'bg-brand-soft text-ink' : 'text-primarytext hover:bg-mist'"
            @click="selectSession(session.id)"
          >
            <span class="min-w-0 flex-1 truncate">{{ session.title ?? "未命名会话" }}</span>
            <span class="hidden rounded p-1 text-secondarytext hover:bg-danger-soft hover:text-danger group-hover:block" @click.stop="removeSession(session.id)">
              <Trash2 class="h-4 w-4" />
            </span>
          </button>
        </div>
      </aside>

      <section class="flex min-h-[72vh] flex-col overflow-hidden rounded-lg border border-navy/20 bg-navy">
        <header class="flex items-center justify-between border-b border-white/10 px-5 py-3.5">
          <p class="font-display text-sm font-bold text-white">ERP/WMS 鉴权问答</p>
          <span class="code-text text-xs text-white/45">
            {{ phase === "streaming" ? "生成中…" : phase === "interrupted" ? "等待补充问题" : "就绪" }}
          </span>
        </header>
        <div class="permission-pulse-line mx-5 mt-1" />

        <div class="thin-scrollbar flex-1 overflow-y-auto px-5 py-4">
          <div v-if="!messages.length" class="py-16 text-center">
            <p class="font-display text-lg font-bold text-white/90">基于您有权访问的 ERP/WMS 产品知识回答</p>
            <p class="mt-2 text-sm text-white/50">订单、商品/SKU、库存、WMS、采购、售后；无权限内容不会进入 Prompt。</p>
          </div>
          <div v-else class="space-y-4">
            <div v-for="(message, index) in messages" :key="index" class="flex" :class="message.role === 'user' ? 'justify-end' : 'justify-start'">
              <div
                class="max-w-[85%] whitespace-pre-wrap rounded-xl px-4 py-3 text-sm leading-relaxed"
                :class="message.role === 'user' ? 'bg-brand text-navy-deep' : 'bg-white/10 text-white/90 ring-1 ring-white/10'"
              >
                <LoaderCircle v-if="message.streaming && !message.content" class="h-4 w-4 animate-spin text-brand" />
                <template v-else>{{ message.content }}</template>
                <p v-if="message.usage" class="code-text mt-2 flex items-center gap-2 text-[11px] text-white/40">
                  <Gauge class="h-3 w-3" />
                  {{ message.usage.total_tokens }} tokens · {{ formatMs(message.usage.response_time_ms) }}
                </p>
              </div>
            </div>
            <div ref="bottom" />
          </div>
        </div>

        <footer class="border-t border-white/10 p-4">
          <p v-if="phase === 'interrupted'" class="mb-2 flex items-center gap-2 text-xs text-review">
            <CircleAlert class="h-3.5 w-3.5" />未找到相关知识——补充说明后发送，将自动续接本轮问答。
          </p>
          <p v-if="sendError" class="mb-2 text-xs text-danger">{{ sendError }}</p>
          <form class="flex gap-2" @submit.prevent="send">
            <input
              v-model="input"
              :maxlength="questionMax"
              :disabled="!activeId || phase === 'streaming'"
              :placeholder="activeId ? '输入问题，如：WMS 库存同步异常怎么排查？' : '请先新建会话'"
              class="h-11 min-w-0 flex-1 rounded-md border border-white/15 bg-white/10 px-3 text-sm text-white placeholder:text-white/35"
            />
            <button
              type="submit"
              :disabled="!input.trim() || phase === 'streaming' || !activeId"
              class="flex h-11 items-center gap-2 rounded-md bg-brand px-4 text-sm font-bold text-navy-deep disabled:opacity-50"
            >
              <LoaderCircle v-if="phase === 'streaming'" class="h-4 w-4 animate-spin" />
              <Send v-else class="h-4 w-4" />发送
            </button>
          </form>
          <p class="mt-1.5 text-right text-[11px] text-white/35">{{ input.length }}/{{ questionMax }}</p>
        </footer>
      </section>

      <aside class="space-y-4">
        <div class="rounded-lg border border-boundary bg-card p-4">
          <p class="flex items-center gap-2 font-display text-sm font-bold text-ink">
            <BookMarked class="h-4 w-4 text-brand" />产品知识引用
          </p>
          <div class="permission-pulse-line mt-3" />
          <p v-if="!citations.length" class="py-6 text-center text-[13px] text-secondarytext">回答引用将在此展示</p>
          <ul v-else class="mt-3 space-y-2">
            <li v-for="citation in citations" :key="citation.chunk_id ?? `${citation.unit_id}-${citation.chunk_index ?? 0}`" class="rounded-md border border-boundary bg-mist/60 px-3 py-2.5">
              <p class="truncate text-[13px] font-medium text-ink" :title="citation.title">{{ citation.title }}</p>
              <p class="code-text mt-0.5 text-[11px] text-secondarytext">
                #{{ citation.unit_id }}
                <template v-if="citation.page_start"> · P{{ citation.page_start }}<template v-if="citation.page_end && citation.page_end !== citation.page_start">-{{ citation.page_end }}</template></template>
                <template v-if="citation.section_path"> · {{ citation.section_path }}</template>
              </p>
              <p v-if="citation.source_file_name" class="mt-1 truncate text-[11px] text-secondarytext/80" :title="citation.source_file_name">
                {{ citation.source_file_name }} · 相似度 {{ (citation.score * 100).toFixed(0) }}%
              </p>
            </li>
          </ul>
        </div>

        <div class="rounded-lg border border-review/40 bg-review-soft p-4">
          <p class="flex items-center gap-2 font-display text-sm font-bold text-ink">
            <Lock class="h-4 w-4 text-review" />无权限单元
          </p>
          <p v-if="!unauthorized.length" class="py-4 text-center text-[13px] text-secondarytext">本轮召回内容均在您的权限范围内</p>
          <ul v-else class="mt-3 space-y-2">
            <li v-for="unit in unauthorized" :key="unit.id" class="rounded-md bg-card px-3 py-2.5">
              <p class="code-text text-[12px] text-ink">知识单元 #{{ unit.id }}</p>
              <p class="mt-0.5 text-[11px] text-secondarytext">
                {{ unit.score != null ? `相似度 ${(unit.score * 100).toFixed(0)}% · ` : "" }}无访问权限，正文已隐藏
              </p>
              <button class="mt-1 text-[12px] font-medium text-review hover:underline" @click="router.push('/knowledge/units')">申请权限 →</button>
            </li>
          </ul>
        </div>
      </aside>
    </div>
  </div>
</template>
