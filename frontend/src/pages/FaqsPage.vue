<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Check, LoaderCircle, Plus, Trash2, X, XCircle } from "lucide-vue-next";

import { ApiError } from "@/api/client";
import {
  createFaq,
  getFaqs,
  offlineFaq,
  reviewFaq,
  type FaqItem,
} from "@/api/settlement";
import PageHeader from "@/components/shared/PageHeader.vue";
import { formatDateTime } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const rows = ref<FaqItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const statusFilter = ref("");
const sourceFilter = ref("");
const loading = ref(false);
const error = ref<string | null>(null);
const createOpen = ref(false);
const reviewing = ref<FaqItem | null>(null);
const reviewAnswer = ref("");
const saving = ref(false);
const form = reactive({ question: "", answer: "", category: "", related_unit_id: "" });
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const response = await getFaqs({
      page: page.value,
      page_size: pageSize,
      status: statusFilter.value ? (statusFilter.value as FaqItem["status"]) : undefined,
      source_type: sourceFilter.value ? (sourceFilter.value as FaqItem["source_type"]) : undefined,
    });
    rows.value = response.items;
    total.value = response.total;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "FAQ 加载失败";
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  form.question = "";
  form.answer = "";
  form.category = "";
  form.related_unit_id = "";
  createOpen.value = true;
}

async function saveCreate() {
  if (form.question.trim().length < 5 || !form.answer.trim()) {
    error.value = "问题至少 5 个字符，答案不能为空";
    return;
  }
  saving.value = true;
  try {
    await createFaq({
      question: form.question.trim(),
      answer: form.answer.trim(),
      category: form.category.trim() || null,
      related_unit_id: form.related_unit_id ? Number(form.related_unit_id) : null,
    });
    createOpen.value = false;
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "FAQ 创建失败";
  } finally {
    saving.value = false;
  }
}

function openReview(item: FaqItem) {
  reviewing.value = item;
  reviewAnswer.value = item.answer;
}

async function review(action: "approve" | "reject") {
  if (!reviewing.value) return;
  saving.value = true;
  try {
    await reviewFaq(reviewing.value.id, action, reviewAnswer.value.trim());
    reviewing.value = null;
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "审核失败";
  } finally {
    saving.value = false;
  }
}

async function remove(item: FaqItem) {
  if (!window.confirm("确认下线并删除 FAQ「" + item.question + "」？")) return;
  try {
    await offlineFaq(item.id);
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "FAQ 删除失败";
  }
}

function refilter() {
  page.value = 1;
  void load();
}

onMounted(() => void load());
</script>

<template>
  <div class="animate-fade-up">
    <PageHeader title="FAQ 审核" description="人工 FAQ 创建后进入 pending_review；审核通过才写入 FAQ 缓存，拒绝或下线会同步清缓存。">
      <template #actions><button v-if="auth.can('faq:write')" class="flex h-10 items-center gap-2 rounded-md bg-brand px-4 text-sm font-bold text-navy-deep" @click="openCreate"><Plus class="h-4 w-4" />新建 FAQ</button></template>
    </PageHeader>

    <section class="mb-4 flex flex-wrap gap-3 rounded-xl border border-boundary bg-card p-4">
      <select v-model="statusFilter" class="h-10 rounded-md border border-boundary bg-white px-3 text-sm" @change="refilter"><option value="">全部状态</option><option value="pending_review">待审核</option><option value="published">已发布</option><option value="rejected">已拒绝</option></select>
      <select v-model="sourceFilter" class="h-10 rounded-md border border-boundary bg-white px-3 text-sm" @change="refilter"><option value="">全部来源</option><option value="manual">人工</option><option value="auto_mined">自动挖掘</option></select>
    </section>

    <div v-if="error" class="mb-4 rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm text-danger">{{ error }}</div>
    <section class="overflow-hidden rounded-xl border border-boundary bg-card">
      <div v-if="loading" class="flex min-h-64 items-center justify-center text-secondarytext"><LoaderCircle class="mr-2 h-5 w-5 animate-spin" />加载中…</div>
      <div v-else-if="!rows.length" class="py-16 text-center text-sm text-secondarytext">暂无 FAQ</div>
      <ul v-else class="divide-y divide-boundary">
        <li v-for="item in rows" :key="item.id" class="p-5 hover:bg-mist/40">
          <div class="flex items-start gap-4">
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-2"><strong class="text-sm text-ink">{{ item.question }}</strong><span class="rounded-full px-2 py-0.5 text-xs" :class="item.status === 'published' ? 'bg-brand-soft text-ink' : item.status === 'pending_review' ? 'bg-review-soft text-review' : 'bg-danger-soft text-danger'">{{ item.status }}</span><span class="code-text text-xs text-secondarytext">{{ item.source_type }}</span></div>
              <p class="mt-2 whitespace-pre-wrap text-sm leading-6 text-primarytext">{{ item.answer }}</p>
              <p class="code-text mt-2 text-xs text-secondarytext">category={{ item.category || "—" }} · unit={{ item.related_unit_id ?? "—" }} · hits={{ item.hit_count }} · {{ formatDateTime(item.updated_at) }}</p>
            </div>
            <div class="flex shrink-0 gap-1">
              <button v-if="item.status === 'pending_review' && auth.can('faq:review')" class="rounded-md border border-brand/40 bg-brand-soft px-3 py-2 text-xs font-medium text-ink" @click="openReview(item)">审核</button>
              <button v-if="auth.can('faq:write')" class="rounded p-2 text-danger hover:bg-danger-soft" title="下线/删除" @click="remove(item)"><Trash2 class="h-4 w-4" /></button>
            </div>
          </div>
        </li>
      </ul>
      <footer class="flex items-center justify-between border-t border-boundary px-4 py-3 text-sm text-secondarytext"><span>共 {{ total }} 条</span><div class="flex items-center gap-2"><button class="rounded border border-boundary px-3 py-1.5 disabled:opacity-40" :disabled="page <= 1" @click="page--; load()">上一页</button><span class="code-text">{{ page }} / {{ totalPages }}</span><button class="rounded border border-boundary px-3 py-1.5 disabled:opacity-40" :disabled="page >= totalPages" @click="page++; load()">下一页</button></div></footer>
    </section>

    <div v-if="createOpen" class="fixed inset-0 z-50 flex justify-end bg-navy-deep/40" @click.self="createOpen = false">
      <aside class="h-full w-full max-w-xl overflow-y-auto bg-mist p-6 shadow-2xl"><div class="flex items-center justify-between"><h2 class="font-display text-xl font-extrabold text-ink">新建 FAQ</h2><button class="rounded p-2 text-secondarytext" @click="createOpen = false"><X class="h-5 w-5" /></button></div><div class="mt-5 space-y-4"><label class="block"><span class="text-xs font-medium text-secondarytext">问题</span><textarea v-model="form.question" rows="3" class="mt-1 w-full rounded-md border border-boundary bg-white p-3 text-sm" /></label><label class="block"><span class="text-xs font-medium text-secondarytext">答案</span><textarea v-model="form.answer" rows="10" class="mt-1 w-full rounded-md border border-boundary bg-white p-3 text-sm" /></label><label class="block"><span class="text-xs font-medium text-secondarytext">分类</span><input v-model.trim="form.category" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm" /></label><label class="block"><span class="text-xs font-medium text-secondarytext">关联知识单元 ID（可选）</span><input v-model="form.related_unit_id" inputmode="numeric" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm" /></label></div><div class="mt-6 flex justify-end gap-2 border-t border-boundary pt-4"><button class="rounded border border-boundary bg-white px-4 py-2 text-sm" @click="createOpen = false">取消</button><button class="rounded bg-brand px-4 py-2 text-sm font-bold text-navy-deep disabled:opacity-50" :disabled="saving" @click="saveCreate">{{ saving ? "提交中…" : "提交审核" }}</button></div></aside>
    </div>

    <div v-if="reviewing" class="fixed inset-0 z-50 flex justify-end bg-navy-deep/40" @click.self="reviewing = null">
      <aside class="h-full w-full max-w-xl overflow-y-auto bg-mist p-6 shadow-2xl"><div class="flex items-center justify-between"><h2 class="font-display text-xl font-extrabold text-ink">审核 FAQ</h2><button class="rounded p-2 text-secondarytext" @click="reviewing = null"><X class="h-5 w-5" /></button></div><p class="mt-5 font-medium text-ink">{{ reviewing.question }}</p><label class="mt-4 block"><span class="text-xs font-medium text-secondarytext">审批后的答案（approve 时可编辑）</span><textarea v-model="reviewAnswer" rows="12" class="mt-1 w-full rounded-md border border-boundary bg-white p-3 text-sm" /></label><div class="mt-6 flex justify-end gap-2 border-t border-boundary pt-4"><button class="flex items-center gap-2 rounded-md border border-danger/30 bg-danger-soft px-4 py-2 text-sm font-medium text-danger disabled:opacity-50" :disabled="saving" @click="review('reject')"><XCircle class="h-4 w-4" />拒绝</button><button class="flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-bold text-navy-deep disabled:opacity-50" :disabled="saving || !reviewAnswer.trim()" @click="review('approve')"><Check class="h-4 w-4" />通过并发布</button></div></aside>
    </div>
  </div>
</template>
