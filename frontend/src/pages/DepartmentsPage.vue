<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { Building2, LoaderCircle, Pencil, Plus, Trash2, X } from "lucide-vue-next";

import { ApiError } from "@/api/client";
import {
  createDepartment,
  deleteDepartment,
  getDepartments,
  updateDepartment,
  type DepartmentNode,
} from "@/api/org";
import PageHeader from "@/components/shared/PageHeader.vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const tree = ref<DepartmentNode[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const editing = ref<DepartmentNode | null>(null);
const panelOpen = ref(false);
const saving = ref(false);
const formError = ref<string | null>(null);
const form = reactive({
  name: "",
  parent_id: "",
  leader_id: "",
  sort_order: 0,
});

interface FlatNode {
  node: DepartmentNode;
  depth: number;
}

function flatten(nodes: DepartmentNode[], depth = 0): FlatNode[] {
  return nodes.flatMap((node) => [
    { node, depth },
    ...flatten(node.children, depth + 1),
  ]);
}

const flat = computed(() => flatten(tree.value));
function collectDescendantIds(node: DepartmentNode | null): Set<number> {
  const ids = new Set<number>();
  function visit(current: DepartmentNode) {
    for (const child of current.children) {
      ids.add(child.id);
      visit(child);
    }
  }
  if (node) visit(node);
  return ids;
}

const parentOptions = computed(() => {
  const descendants = collectDescendantIds(editing.value);
  return flat.value.filter(
    (item) => item.node.id !== editing.value?.id && !descendants.has(item.node.id),
  );
});

async function load() {
  loading.value = true;
  try {
    tree.value = await getDepartments();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "业务团队加载失败";
  } finally {
    loading.value = false;
  }
}

function openCreate(parentId: number | null = null) {
  editing.value = null;
  form.name = "";
  form.parent_id = parentId == null ? "" : String(parentId);
  form.leader_id = "";
  form.sort_order = 0;
  formError.value = null;
  panelOpen.value = true;
}

function openEdit(node: DepartmentNode) {
  editing.value = node;
  form.name = node.name;
  form.parent_id = node.parent_id == null ? "" : String(node.parent_id);
  form.leader_id = node.leader_id == null ? "" : String(node.leader_id);
  form.sort_order = node.sort_order;
  formError.value = null;
  panelOpen.value = true;
}

async function save() {
  if (!form.name.trim()) {
    formError.value = "团队名称不能为空";
    return;
  }
  saving.value = true;
  formError.value = null;
  const payload = {
    name: form.name.trim(),
    parent_id: form.parent_id ? Number(form.parent_id) : null,
    leader_id: form.leader_id ? Number(form.leader_id) : null,
    sort_order: Number(form.sort_order) || 0,
  };
  try {
    if (editing.value) await updateDepartment(editing.value.id, payload);
    else await createDepartment(payload);
    panelOpen.value = false;
    await load();
  } catch (err) {
    formError.value = err instanceof ApiError ? err.message : "保存失败";
  } finally {
    saving.value = false;
  }
}

async function remove(node: DepartmentNode) {
  if (!window.confirm("确认删除业务团队「" + node.name + "」？有子团队或成员时后端会拒绝删除。")) return;
  try {
    await deleteDepartment(node.id);
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "删除失败";
  }
}

onMounted(() => void load());
</script>

<template>
  <div class="animate-fade-up">
    <PageHeader title="业务团队" description="维护产品中心、实施交付、商家客服与客户成功组织树；删除时后端保护有子部门或成员的节点。">
      <template #actions><button v-if="auth.can('dept:write')" class="flex h-10 items-center gap-2 rounded-md bg-brand px-4 text-sm font-bold text-navy-deep" @click="openCreate()"><Plus class="h-4 w-4" />新增团队</button></template>
    </PageHeader>
    <div v-if="error" class="mb-4 rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm text-danger">{{ error }}</div>
    <section class="overflow-hidden rounded-xl border border-boundary bg-card">
      <div v-if="loading" class="flex min-h-64 items-center justify-center text-secondarytext"><LoaderCircle class="mr-2 h-5 w-5 animate-spin" />加载中…</div>
      <div v-else-if="!flat.length" class="py-16 text-center text-sm text-secondarytext">暂无业务团队</div>
      <ul v-else class="divide-y divide-boundary">
        <li v-for="item in flat" :key="item.node.id" class="flex items-center gap-3 px-5 py-3 hover:bg-mist/60">
          <div class="flex min-w-0 flex-1 items-center gap-3" :style="{ paddingLeft: item.depth * 24 + 'px' }">
            <span class="flex h-8 w-8 items-center justify-center rounded-md bg-brand-soft text-ink"><Building2 class="h-4 w-4" /></span>
            <div><p class="font-medium text-ink">{{ item.node.name }}</p><p class="code-text text-secondarytext">ID {{ item.node.id }} · sort {{ item.node.sort_order }} · {{ item.node.member_count }} members</p></div>
          </div>
          <div v-if="auth.can('dept:write')" class="flex gap-1">
            <button class="rounded p-2 text-secondarytext hover:bg-mist hover:text-ink" title="新增子团队" @click="openCreate(item.node.id)"><Plus class="h-4 w-4" /></button>
            <button class="rounded p-2 text-secondarytext hover:bg-mist hover:text-ink" title="编辑" @click="openEdit(item.node)"><Pencil class="h-4 w-4" /></button>
            <button class="rounded p-2 text-danger hover:bg-danger-soft" title="删除" @click="remove(item.node)"><Trash2 class="h-4 w-4" /></button>
          </div>
        </li>
      </ul>
    </section>

    <div v-if="panelOpen" class="fixed inset-0 z-50 flex justify-end bg-navy-deep/40" @click.self="panelOpen = false">
      <aside class="h-full w-full max-w-md bg-mist p-6 shadow-2xl">
        <div class="flex items-center justify-between"><h2 class="font-display text-xl font-extrabold text-ink">{{ editing ? "编辑业务团队" : "新增业务团队" }}</h2><button class="rounded p-2 text-secondarytext" @click="panelOpen = false"><X class="h-5 w-5" /></button></div>
        <div v-if="formError" class="mt-4 rounded-md border border-danger/30 bg-danger-soft p-3 text-sm text-danger">{{ formError }}</div>
        <div class="mt-5 space-y-4">
          <label class="block"><span class="text-xs font-medium text-secondarytext">团队名称</span><input v-model.trim="form.name" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm" /></label>
          <label class="block"><span class="text-xs font-medium text-secondarytext">上级团队</span><select v-model="form.parent_id" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm"><option value="">顶级团队</option><option v-for="item in parentOptions" :key="item.node.id" :value="String(item.node.id)">{{ "—".repeat(item.depth) }} {{ item.node.name }}</option></select></label>
          <label class="block"><span class="text-xs font-medium text-secondarytext">负责人用户 ID（可选）</span><input v-model="form.leader_id" inputmode="numeric" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm" placeholder="留空表示未设置" /></label>
          <label class="block"><span class="text-xs font-medium text-secondarytext">排序值</span><input v-model.number="form.sort_order" type="number" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm" /></label>
        </div>
        <div class="mt-6 flex justify-end gap-2 border-t border-boundary pt-4"><button class="rounded-md border border-boundary bg-white px-4 py-2 text-sm" @click="panelOpen = false">取消</button><button class="flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-bold text-navy-deep disabled:opacity-50" :disabled="saving" @click="save"><LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" />保存</button></div>
      </aside>
    </div>
  </div>
</template>
