<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { FilePlus2, LoaderCircle, Target, X } from "lucide-vue-next";
import { useRouter } from "vue-router";

import { ApiError } from "@/api/client";
import { createUnitFromGap, getGaps, type GapItem } from "@/api/settlement";
import PageHeader from "@/components/shared/PageHeader.vue";
import { formatDateTime } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const router = useRouter();
const rows = ref<GapItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const statusFilter = ref("");
const loading = ref(false);
const saving = ref(false);
const error = ref<string | null>(null);
const selected = ref<GapItem | null>(null);
const createdUnitId = ref<number | null>(null);
const form = reactive({ title: "", category: "", summary: "", content: "" });
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));

async function load() {
  loading.value = true;
  try {
    const response = await getGaps({
      page: page.value,
      page_size: pageSize,
      status: statusFilter.value ? (statusFilter.value as GapItem["status"]) : undefined,
    });
    rows.value = response.items;
    total.value = response.total;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "知识缺口加载失败";
  } finally {
    loading.value = false;
  }
}

function openCreate(item: GapItem) {
  selected.value = item;
  createdUnitId.value = null;
  form.title = item.question_pattern;
  form.category = "knowledge_gap";
  form.summary = item.sample_questions_json[0] ?? item.question_pattern;
  form.content = item.sample_questions_json.join("\n");
}

async function createUnit() {
  if (!selected.value || !form.title.trim()) return;
  saving.value = true;
  error.value = null;
  try {
    const response = await createUnitFromGap(selected.value.id, {
      title: form.title.trim(),
      category: form.category.trim() || null,
      summary: form.summary.trim() || null,
      content: form.content.trim() || null,
    });
    createdUnitId.value = response.unit_id;
    await load();
  } catch (err) {
    error.value =
      err instanceof ApiError
        ? err.message
        : "一键建档失败；索引失败时缺口不会提前标记 resolved";
  } finally {
    saving.value = false;
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
    <PageHeader title="知识缺口" description="聚合低召回问题；一键建档采用最小权限，先仅创建者可见，完成单 unit 索引后才把缺口标记为 resolved。" />
    <section class="mb-4 flex gap-3 rounded-xl border border-boundary bg-card p-4"><select v-model="statusFilter" class="h-10 rounded-md border border-boundary bg-white px-3 text-sm" @change="refilter"><option value="">全部状态</option><option value="unresolved">未解决</option><option value="resolved">已解决</option><option value="ignored">已忽略</option></select></section>
    <div v-if="error" class="mb-4 rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm text-danger">{{ error }}</div>

    <section class="overflow-hidden rounded-xl border border-boundary bg-card">
      <div v-if="loading" class="flex min-h-64 items-center justify-center text-secondarytext"><LoaderCircle class="mr-2 h-5 w-5 animate-spin" />加载中…</div>
      <div v-else-if="!rows.length" class="py-16 text-center text-sm text-secondarytext">暂无知识缺口</div>
      <ul v-else class="divide-y divide-boundary">
        <li v-for="item in rows" :key="item.id" class="p-5 hover:bg-mist/50">
          <div class="flex items-start gap-4">
            <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-review-soft text-review"><Target class="h-5 w-5" /></span>
            <div class="min-w-0 flex-1"><div class="flex flex-wrap items-center gap-2"><strong class="text-sm text-ink">{{ item.question_pattern }}</strong><span class="rounded-full px-2 py-0.5 text-xs" :class="item.status === 'resolved' ? 'bg-brand-soft text-ink' : 'bg-review-soft text-review'">{{ item.status }}</span></div><p class="mt-2 text-sm text-secondarytext">{{ item.sample_questions_json.slice(0, 3).join("；") || "暂无样例问题" }}</p><p class="code-text mt-2 text-xs text-secondarytext">ask_count={{ item.ask_count }} · last={{ formatDateTime(item.last_asked_at) }} · resolved_unit={{ item.resolved_unit_id ?? "—" }}</p></div>
            <button v-if="item.status === 'unresolved' && auth.can('knowledge:write')" class="flex shrink-0 items-center gap-2 rounded-md bg-brand px-3 py-2 text-xs font-bold text-navy-deep" @click="openCreate(item)"><FilePlus2 class="h-4 w-4" />一键建档</button>
          </div>
        </li>
      </ul>
      <footer class="flex items-center justify-between border-t border-boundary px-4 py-3 text-sm text-secondarytext"><span>共 {{ total }} 条</span><div class="flex items-center gap-2"><button class="rounded border border-boundary px-3 py-1.5 disabled:opacity-40" :disabled="page <= 1" @click="page--; load()">上一页</button><span class="code-text">{{ page }} / {{ totalPages }}</span><button class="rounded border border-boundary px-3 py-1.5 disabled:opacity-40" :disabled="page >= totalPages" @click="page++; load()">下一页</button></div></footer>
    </section>

    <div v-if="selected" class="fixed inset-0 z-50 flex justify-end bg-navy-deep/40" @click.self="selected = null">
      <aside class="h-full w-full max-w-xl overflow-y-auto bg-mist p-6 shadow-2xl">
        <div class="flex items-center justify-between"><h2 class="font-display text-xl font-extrabold text-ink">从知识缺口建档</h2><button class="rounded p-2 text-secondarytext" @click="selected = null"><X class="h-5 w-5" /></button></div>
        <div v-if="createdUnitId" class="mt-4 rounded-lg border border-brand/40 bg-brand-soft p-4"><p class="font-medium text-ink">建档成功：知识单元 #{{ createdUnitId }}</p><p class="mt-1 text-xs text-secondarytext">新单元默认仅创建者可见；可到知识资产页继续审核并扩大权限范围。</p><button class="mt-3 text-sm font-medium text-ink underline" @click="router.push('/knowledge/units')">前往知识资产 →</button></div>
        <template v-else>
          <p class="mt-4 rounded-md bg-review-soft p-3 text-xs leading-5 text-primarytext">该操作不会直接生成全局可见知识。后端先创建 user 级权限、完成索引，成功后才 resolve gap。</p>
          <div class="mt-5 space-y-4"><label class="block"><span class="text-xs font-medium text-secondarytext">标题</span><input v-model.trim="form.title" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm" /></label><label class="block"><span class="text-xs font-medium text-secondarytext">分类</span><input v-model.trim="form.category" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm" /></label><label class="block"><span class="text-xs font-medium text-secondarytext">摘要</span><textarea v-model="form.summary" rows="3" class="mt-1 w-full rounded-md border border-boundary bg-white p-3 text-sm" /></label><label class="block"><span class="text-xs font-medium text-secondarytext">正文</span><textarea v-model="form.content" rows="12" class="mt-1 w-full rounded-md border border-boundary bg-white p-3 text-sm" /></label></div>
          <div class="mt-6 flex justify-end gap-2 border-t border-boundary pt-4"><button class="rounded border border-boundary bg-white px-4 py-2 text-sm" @click="selected = null">取消</button><button class="flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-bold text-navy-deep disabled:opacity-50" :disabled="saving || !form.title.trim()" @click="createUnit"><LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" />创建并建立索引</button></div>
        </template>
      </aside>
    </div>
  </div>
</template>
