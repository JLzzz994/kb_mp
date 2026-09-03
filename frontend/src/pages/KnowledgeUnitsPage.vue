<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import {
  AlertCircle,
  CheckCircle2,
  DatabaseZap,
  FileSearch,
  LoaderCircle,
  RefreshCw,
  Save,
  Search,
  Trash2,
  X,
} from "lucide-vue-next";

import { ApiError } from "@/api/client";
import {
  batchDeleteUnits,
  getKnowledgeIndexStatus,
  getKnowledgeUnit,
  getKnowledgeUnits,
  patchKnowledgeUnit,
  reindexKnowledgeUnit,
  type KnowledgeIndexStatus,
  type KnowledgeUnitDetail,
  type KnowledgeUnitItem,
  type PermissionEntry,
} from "@/api/knowledge";
import KnowledgePermissionEditor from "@/components/knowledge/KnowledgePermissionEditor.vue";
import PageHeader from "@/components/shared/PageHeader.vue";
import { formatDateTime } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();

const rows = ref<KnowledgeUnitItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const keyword = ref("");
const status = ref("");
const loading = ref(false);
const error = ref<string | null>(null);

const detail = ref<KnowledgeUnitDetail | null>(null);
const detailLoading = ref(false);
const saving = ref(false);
const deleting = ref(false);
const reindexing = ref(false);
const indexStatus = ref<KnowledgeIndexStatus | null>(null);
const panelError = ref<string | null>(null);

const edit = reactive({ title: "", category: "", summary: "", content: "" });
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const response = await getKnowledgeUnits({
      page: page.value,
      page_size: pageSize,
      keyword: keyword.value || undefined,
      status: status.value || undefined,
    });
    rows.value = response.items;
    total.value = response.total;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "知识资产加载失败";
  } finally {
    loading.value = false;
  }
}

async function openDetail(id: number) {
  detailLoading.value = true;
  panelError.value = null;
  indexStatus.value = null;
  try {
    const [unit, health] = await Promise.all([
      getKnowledgeUnit(id),
      getKnowledgeIndexStatus(id).catch(() => null),
    ]);
    detail.value = unit;
    indexStatus.value = health;
    edit.title = unit.title;
    edit.category = unit.category ?? "";
    edit.summary = unit.summary ?? "";
    edit.content = unit.content;
  } catch (err) {
    panelError.value = err instanceof ApiError ? err.message : "知识详情加载失败";
  } finally {
    detailLoading.value = false;
  }
}

async function save() {
  if (!detail.value) return;
  saving.value = true;
  panelError.value = null;
  try {
    const updated = await patchKnowledgeUnit(detail.value.id, {
      title: edit.title.trim(),
      category: edit.category.trim(),
      summary: edit.summary.trim(),
      content: edit.content,
    });
    detail.value = await getKnowledgeUnit(updated.id);
    edit.title = detail.value.title;
    edit.category = detail.value.category ?? "";
    edit.summary = detail.value.summary ?? "";
    edit.content = detail.value.content;
    indexStatus.value = await getKnowledgeIndexStatus(updated.id).catch(() => null);
    await load();
  } catch (err) {
    panelError.value =
      err instanceof ApiError
        ? `${err.message}${err.errorCode === "knowledge_index_sync_failed" ? "（正文已保存为 vector_pending，可稍后重建索引）" : ""}`
        : "保存失败";
    if (detail.value) {
      indexStatus.value = await getKnowledgeIndexStatus(detail.value.id).catch(() => null);
    }
  } finally {
    saving.value = false;
  }
}

async function reindex() {
  if (!detail.value) return;
  reindexing.value = true;
  panelError.value = null;
  try {
    indexStatus.value = await reindexKnowledgeUnit(detail.value.id);
    detail.value = await getKnowledgeUnit(detail.value.id);
    await load();
  } catch (err) {
    panelError.value = err instanceof ApiError ? err.message : "索引重建失败";
  } finally {
    reindexing.value = false;
  }
}

async function remove() {
  if (!detail.value || !window.confirm(`确认删除知识单元「${detail.value.title}」？`)) return;
  deleting.value = true;
  try {
    await batchDeleteUnits([detail.value.id]);
    detail.value = null;
    indexStatus.value = null;
    await load();
  } catch (err) {
    panelError.value = err instanceof ApiError ? err.message : "删除失败";
  } finally {
    deleting.value = false;
  }
}

async function handlePermissionsSaved(permissions: PermissionEntry[]) {
  if (!detail.value) return;
  detail.value = {
    ...detail.value,
    permissions,
    permissions_summary:
      permissions.length === 1 && permissions[0]?.target_type === "global"
        ? "全局公开"
        : permissions
            .slice(0, 3)
            .map((item) => item.target_label || item.target_type)
            .join(" + ") + (permissions.length > 3 ? "…" : ""),
  };
  panelError.value = null;
  await load();
}

function submitSearch() {
  page.value = 1;
  void load();
}

function statusLabel(value: KnowledgeUnitItem["status"]): string {
  if (value === "active") return "可检索";
  if (value === "vector_pending") return "待向量化";
  return "失败";
}

onMounted(() => void load());
</script>

<template>
  <div class="animate-fade-up">
    <PageHeader
      title="知识资产"
      description="管理 ERP/WMS 产品知识正文、版本状态、来源文件、权限摘要与 Milvus chunk 索引健康。"
    />

    <section class="mb-4 flex flex-col gap-3 rounded-xl border border-boundary bg-card p-4 sm:flex-row">
      <form class="flex min-w-0 flex-1 gap-2" @submit.prevent="submitSearch">
        <div class="relative min-w-0 flex-1">
          <Search class="absolute left-3 top-3 h-4 w-4 text-secondarytext" aria-hidden="true" />
          <input
            v-model.trim="keyword"
            class="h-10 w-full rounded-md border border-boundary bg-white pl-9 pr-3 text-sm"
            placeholder="按标题、内容或来源搜索"
          />
        </div>
        <button class="rounded-md bg-ink px-4 text-sm font-medium text-white">搜索</button>
      </form>
      <select v-model="status" class="h-10 rounded-md border border-boundary bg-white px-3 text-sm" @change="submitSearch">
        <option value="">全部状态</option>
        <option value="active">active</option>
        <option value="vector_pending">vector_pending</option>
        <option value="failed">failed</option>
      </select>
    </section>

    <div v-if="error" class="mb-4 rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm text-danger">{{ error }}</div>

    <section class="overflow-hidden rounded-xl border border-boundary bg-card">
      <div v-if="loading" class="flex min-h-64 items-center justify-center text-secondarytext">
        <LoaderCircle class="mr-2 h-5 w-5 animate-spin" />加载中…
      </div>
      <div v-else-if="!rows.length" class="py-16 text-center text-sm text-secondarytext">暂无知识资产</div>
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[900px] text-left text-sm">
          <thead class="bg-mist text-xs text-secondarytext">
            <tr>
              <th class="px-4 py-3 font-medium">知识单元</th>
              <th class="px-4 py-3 font-medium">业务分类</th>
              <th class="px-4 py-3 font-medium">状态</th>
              <th class="px-4 py-3 font-medium">权限</th>
              <th class="px-4 py-3 font-medium">来源</th>
              <th class="px-4 py-3 font-medium">更新时间</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-boundary">
            <tr v-for="row in rows" :key="row.id" class="cursor-pointer hover:bg-mist/70" @click="openDetail(row.id)">
              <td class="px-4 py-3">
                <p class="font-medium text-ink">{{ row.title }}</p>
                <p class="code-text mt-0.5 text-secondarytext">{{ row.unit_code }}</p>
              </td>
              <td class="px-4 py-3 text-secondarytext">{{ row.category ?? "—" }}</td>
              <td class="px-4 py-3">
                <span
                  class="rounded-full px-2.5 py-1 text-xs font-semibold"
                  :class="row.status === 'active' ? 'bg-brand-soft text-ink' : 'bg-review-soft text-review'"
                >
                  {{ statusLabel(row.status) }}
                </span>
              </td>
              <td class="px-4 py-3 text-secondarytext">{{ row.permissions_summary || "未配置" }}</td>
              <td class="max-w-48 truncate px-4 py-3 text-secondarytext" :title="row.source_file_name ?? ''">
                {{ row.source_file_name ?? row.file_type ?? "手工知识" }}
              </td>
              <td class="px-4 py-3 text-xs text-secondarytext">{{ formatDateTime(row.updated_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="flex items-center justify-between border-t border-boundary px-4 py-3 text-sm text-secondarytext">
        <span>共 {{ total }} 条</span>
        <div class="flex items-center gap-2">
          <button class="rounded border border-boundary px-3 py-1.5 disabled:opacity-40" :disabled="page <= 1" @click="page--; load()">上一页</button>
          <span class="code-text">{{ page }} / {{ pages }}</span>
          <button class="rounded border border-boundary px-3 py-1.5 disabled:opacity-40" :disabled="page >= pages" @click="page++; load()">下一页</button>
        </div>
      </footer>
    </section>

    <div v-if="detail || detailLoading" class="fixed inset-0 z-50 flex justify-end bg-navy-deep/35" @click.self="detail = null">
      <aside class="h-full w-full max-w-2xl overflow-y-auto bg-mist p-5 shadow-2xl">
        <div class="flex items-center justify-between">
          <h2 class="font-display text-xl font-extrabold text-ink">知识单元详情</h2>
          <button class="rounded-md p-2 text-secondarytext hover:bg-boundary/50" @click="detail = null">
            <X class="h-5 w-5" />
          </button>
        </div>

        <div v-if="detailLoading" class="flex min-h-60 items-center justify-center text-secondarytext">
          <LoaderCircle class="mr-2 h-5 w-5 animate-spin" />加载详情…
        </div>

        <template v-else-if="detail">
          <div
            v-if="indexStatus"
            class="mt-5 rounded-xl border p-4"
            :class="indexStatus.consistent ? 'border-brand/40 bg-brand-soft' : 'border-review/50 bg-review-soft'"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="flex items-center gap-2 font-display font-bold text-ink">
                  <CheckCircle2 v-if="indexStatus.consistent" class="h-4 w-4 text-brand" />
                  <AlertCircle v-else class="h-4 w-4 text-review" />
                  向量索引：{{ indexStatus.consistent ? "一致" : "需要处理" }}
                </p>
                <p class="code-text mt-1 text-secondarytext">
                  DB={{ indexStatus.db_status }} · chunks={{ indexStatus.chunk_count ?? "未启用" }} · {{ indexStatus.detail }}
                </p>
              </div>
              <button
                v-if="auth.can('knowledge:write')"
                class="flex items-center gap-1 rounded-md border border-boundary bg-white px-3 py-2 text-xs font-medium text-ink"
                :disabled="reindexing"
                @click="reindex"
              >
                <RefreshCw class="h-3.5 w-3.5" :class="{ 'animate-spin': reindexing }" />
                {{ reindexing ? "重建中" : "重建索引" }}
              </button>
            </div>
          </div>

          <div v-if="panelError" class="mt-4 rounded-lg border border-danger/30 bg-danger-soft p-3 text-sm text-danger">
            {{ panelError }}
          </div>

          <div class="mt-5 space-y-4">
            <label class="block">
              <span class="text-xs font-medium text-secondarytext">标题</span>
              <input v-model="edit.title" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm" :disabled="!auth.can('knowledge:write')" />
            </label>
            <div class="grid gap-4 sm:grid-cols-2">
              <label>
                <span class="text-xs font-medium text-secondarytext">分类</span>
                <input v-model="edit.category" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm" :disabled="!auth.can('knowledge:write')" />
              </label>
              <div>
                <span class="text-xs font-medium text-secondarytext">来源文件</span>
                <p class="code-text mt-2 text-ink">{{ detail.source_file_name ?? "手工知识" }}</p>
              </div>
            </div>
            <label class="block">
              <span class="text-xs font-medium text-secondarytext">摘要</span>
              <textarea v-model="edit.summary" rows="3" class="mt-1 w-full rounded-md border border-boundary bg-white p-3 text-sm" :disabled="!auth.can('knowledge:write')" />
            </label>
            <label class="block">
              <span class="text-xs font-medium text-secondarytext">正文</span>
              <textarea v-model="edit.content" rows="14" class="code-text mt-1 w-full rounded-md border border-boundary bg-white p-3 leading-6" :disabled="!auth.can('knowledge:write')" />
            </label>

            <div>
              <p class="text-xs font-medium text-secondarytext">当前权限范围</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <span
                  v-for="permission in detail.permissions"
                  :key="`${permission.target_type}-${permission.target_id}`"
                  class="rounded-full bg-white px-3 py-1 text-xs text-ink ring-1 ring-boundary"
                >
                  {{ permission.target_type }} · {{ permission.target_label }}
                </span>
                <span v-if="!detail.permissions.length" class="text-xs text-secondarytext">未配置</span>
              </div>
            </div>

            <KnowledgePermissionEditor
              v-if="auth.can('knowledge:assign_permission')"
              :unit-id="detail.id"
              :permissions="detail.permissions"
              @saved="handlePermissionsSaved"
            />
          </div>

          <div class="mt-6 flex flex-wrap justify-end gap-2 border-t border-boundary pt-4">
            <button
              v-if="auth.can('knowledge:delete')"
              class="flex items-center gap-2 rounded-md border border-danger/30 bg-danger-soft px-4 py-2 text-sm font-medium text-danger"
              :disabled="deleting"
              @click="remove"
            >
              <Trash2 class="h-4 w-4" />{{ deleting ? "删除中…" : "删除" }}
            </button>
            <button
              v-if="auth.can('knowledge:write')"
              class="flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-bold text-navy-deep disabled:opacity-50"
              :disabled="saving"
              @click="save"
            >
              <Save class="h-4 w-4" />{{ saving ? "保存中…" : "保存并同步索引" }}
            </button>
          </div>
        </template>
        <div v-else class="mt-10 flex items-center justify-center text-secondarytext">
          <FileSearch class="mr-2 h-5 w-5" />请选择知识单元
        </div>
      </aside>
    </div>

    <div class="mt-4 flex items-center gap-2 text-xs text-secondarytext">
      <DatabaseZap class="h-4 w-4 text-brand" />
      正文变更采用 unit 级增量重建；title/category 仅同步 chunk 元数据，不重复 Embedding。
    </div>
  </div>
</template>
