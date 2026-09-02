<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { KeyRound, LoaderCircle, Pencil, Plus, Search, UserCheck, UserX, X } from "lucide-vue-next";

import { ApiError } from "@/api/client";
import {
  createUser,
  getDepartments,
  getRoles,
  getUsers,
  patchUserStatus,
  resetPassword,
  updateUser,
  type DepartmentNode,
  type RoleItem,
  type UserItem,
} from "@/api/org";
import PageHeader from "@/components/shared/PageHeader.vue";
import { formatDateTime } from "@/lib/utils";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const users = ref<UserItem[]>([]);
const departments = ref<DepartmentNode[]>([]);
const roles = ref<RoleItem[]>([]);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const keyword = ref("");
const departmentFilter = ref("");
const statusFilter = ref("");
const loading = ref(false);
const error = ref<string | null>(null);

type Mode = "create" | "edit";
const mode = ref<Mode | null>(null);
const editingId = ref<number | null>(null);
const saving = ref(false);
const formError = ref<string | null>(null);
const form = reactive({
  username: "",
  password: "",
  display_name: "",
  department_id: "",
  role_ids: [] as number[],
  status: 1 as 0 | 1,
});

interface DepartmentOption {
  id: number;
  label: string;
}

function flattenDepartments(nodes: DepartmentNode[], depth = 0): DepartmentOption[] {
  return nodes.flatMap((node) => [
    { id: node.id, label: "—".repeat(depth) + (depth ? " " : "") + node.name },
    ...flattenDepartments(node.children, depth + 1),
  ]);
}

const departmentOptions = computed(() => flattenDepartments(departments.value));
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)));

async function load() {
  loading.value = true;
  error.value = null;
  try {
    const response = await getUsers({
      page: page.value,
      page_size: pageSize,
      keyword: keyword.value || undefined,
      department_id: departmentFilter.value ? Number(departmentFilter.value) : undefined,
      status:
        statusFilter.value === ""
          ? undefined
          : (Number(statusFilter.value) as 0 | 1),
    });
    users.value = response.items;
    total.value = response.total;
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "用户列表加载失败";
  } finally {
    loading.value = false;
  }
}

async function loadOptions() {
  const [deptRows, roleRows] = await Promise.all([getDepartments(), getRoles()]);
  departments.value = deptRows;
  roles.value = roleRows;
}

function openCreate() {
  mode.value = "create";
  editingId.value = null;
  form.username = "";
  form.password = "";
  form.display_name = "";
  form.department_id = departmentOptions.value[0] ? String(departmentOptions.value[0].id) : "";
  form.role_ids = [];
  form.status = 1;
  formError.value = null;
}

function openEdit(user: UserItem) {
  mode.value = "edit";
  editingId.value = user.id;
  form.username = user.username;
  form.password = "";
  form.display_name = user.display_name;
  form.department_id = String(user.department_id);
  form.role_ids = roles.value
    .filter((role) => user.role_codes.includes(role.role_code))
    .map((role) => role.id);
  form.status = user.status === 1 ? 1 : 0;
  formError.value = null;
}

async function save() {
  if (!form.display_name.trim() || !form.department_id || !form.role_ids.length) {
    formError.value = "姓名、部门和至少一个角色为必填项";
    return;
  }
  if (mode.value === "create" && (form.username.length < 3 || form.password.length < 8)) {
    formError.value = "新建用户需要至少 3 位用户名和至少 8 位密码";
    return;
  }
  saving.value = true;
  formError.value = null;
  try {
    if (mode.value === "create") {
      await createUser({
        username: form.username.trim(),
        password: form.password,
        display_name: form.display_name.trim(),
        department_id: Number(form.department_id),
        role_ids: form.role_ids,
      });
    } else if (editingId.value != null) {
      await updateUser(editingId.value, {
        display_name: form.display_name.trim(),
        department_id: Number(form.department_id),
        role_ids: form.role_ids,
        status: form.status,
      });
    }
    mode.value = null;
    await load();
  } catch (err) {
    formError.value = err instanceof ApiError ? err.message : "保存失败";
  } finally {
    saving.value = false;
  }
}

async function toggleStatus(user: UserItem) {
  const next = user.status === 1 ? 0 : 1;
  if (!window.confirm("确认" + (next === 1 ? "启用" : "停用") + "用户「" + user.display_name + "」？")) {
    return;
  }
  try {
    await patchUserStatus(user.id, next);
    await load();
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "状态更新失败";
  }
}

async function doResetPassword(user: UserItem) {
  const value = window.prompt("为「" + user.display_name + "」设置新密码（至少 8 位）");
  if (!value) return;
  if (value.length < 8) {
    error.value = "新密码至少 8 位";
    return;
  }
  try {
    await resetPassword(user.id, value);
    error.value = null;
    window.alert("密码已重置，相关鉴权位图已失效。");
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "密码重置失败";
  }
}

function search() {
  page.value = 1;
  void load();
}

onMounted(async () => {
  try {
    await loadOptions();
  } catch {
    error.value = "部门/角色选项加载失败";
  }
  await load();
});
</script>

<template>
  <div class="animate-fade-up">
    <PageHeader title="用户管理" description="管理产品、实施、商家客服与客户成功团队账号；角色或状态变更会使 Redis 鉴权位图失效。">
      <template #actions>
        <button
          v-if="auth.can('user:write')"
          class="flex h-10 items-center gap-2 rounded-md bg-brand px-4 text-sm font-bold text-navy-deep"
          @click="openCreate"
        >
          <Plus class="h-4 w-4" />新建用户
        </button>
      </template>
    </PageHeader>

    <section class="mb-4 grid gap-3 rounded-xl border border-boundary bg-card p-4 md:grid-cols-[minmax(0,1fr)_200px_140px]">
      <form class="flex gap-2" @submit.prevent="search">
        <div class="relative min-w-0 flex-1">
          <Search class="absolute left-3 top-3 h-4 w-4 text-secondarytext" />
          <input v-model.trim="keyword" class="h-10 w-full rounded-md border border-boundary pl-9 pr-3 text-sm" placeholder="用户名或姓名" />
        </div>
        <button class="rounded-md bg-ink px-4 text-sm font-medium text-white">搜索</button>
      </form>
      <select v-model="departmentFilter" class="h-10 rounded-md border border-boundary bg-white px-3 text-sm" @change="search">
        <option value="">全部业务团队</option>
        <option v-for="item in departmentOptions" :key="item.id" :value="String(item.id)">{{ item.label }}</option>
      </select>
      <select v-model="statusFilter" class="h-10 rounded-md border border-boundary bg-white px-3 text-sm" @change="search">
        <option value="">全部状态</option>
        <option value="1">启用</option>
        <option value="0">停用</option>
      </select>
    </section>

    <div v-if="error" class="mb-4 rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm text-danger">{{ error }}</div>

    <section class="overflow-hidden rounded-xl border border-boundary bg-card">
      <div v-if="loading" class="flex min-h-64 items-center justify-center text-secondarytext"><LoaderCircle class="mr-2 h-5 w-5 animate-spin" />加载中…</div>
      <div v-else-if="!users.length" class="py-16 text-center text-sm text-secondarytext">暂无用户</div>
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[900px] text-left text-sm">
          <thead class="bg-mist text-xs text-secondarytext">
            <tr><th class="px-4 py-3">用户</th><th class="px-4 py-3">团队</th><th class="px-4 py-3">角色</th><th class="px-4 py-3">状态</th><th class="px-4 py-3">更新时间</th><th class="px-4 py-3 text-right">操作</th></tr>
          </thead>
          <tbody class="divide-y divide-boundary">
            <tr v-for="user in users" :key="user.id" class="hover:bg-mist/60">
              <td class="px-4 py-3"><p class="font-medium text-ink">{{ user.display_name }}</p><p class="code-text text-secondarytext">{{ user.username }}</p></td>
              <td class="px-4 py-3 text-secondarytext">{{ user.department_name }}</td>
              <td class="px-4 py-3"><div class="flex flex-wrap gap-1"><span v-for="code in user.role_codes" :key="code" class="rounded-full bg-brand-soft px-2 py-0.5 text-xs text-ink">{{ code }}</span></div></td>
              <td class="px-4 py-3"><span class="rounded-full px-2.5 py-1 text-xs font-semibold" :class="user.status === 1 ? 'bg-brand-soft text-ink' : 'bg-danger-soft text-danger'">{{ user.status === 1 ? "启用" : "停用" }}</span></td>
              <td class="px-4 py-3 text-xs text-secondarytext">{{ formatDateTime(user.updated_at) }}</td>
              <td class="px-4 py-3">
                <div v-if="auth.can('user:write')" class="flex justify-end gap-1">
                  <button class="rounded p-2 text-secondarytext hover:bg-mist hover:text-ink" title="编辑" @click="openEdit(user)"><Pencil class="h-4 w-4" /></button>
                  <button class="rounded p-2 text-secondarytext hover:bg-mist hover:text-ink" title="重置密码" @click="doResetPassword(user)"><KeyRound class="h-4 w-4" /></button>
                  <button class="rounded p-2" :class="user.status === 1 ? 'text-danger hover:bg-danger-soft' : 'text-brand hover:bg-brand-soft'" :title="user.status === 1 ? '停用' : '启用'" @click="toggleStatus(user)">
                    <UserX v-if="user.status === 1" class="h-4 w-4" /><UserCheck v-else class="h-4 w-4" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <footer class="flex items-center justify-between border-t border-boundary px-4 py-3 text-sm text-secondarytext">
        <span>共 {{ total }} 个用户</span>
        <div class="flex items-center gap-2"><button class="rounded border border-boundary px-3 py-1.5 disabled:opacity-40" :disabled="page <= 1" @click="page--; load()">上一页</button><span class="code-text">{{ page }} / {{ totalPages }}</span><button class="rounded border border-boundary px-3 py-1.5 disabled:opacity-40" :disabled="page >= totalPages" @click="page++; load()">下一页</button></div>
      </footer>
    </section>

    <div v-if="mode" class="fixed inset-0 z-50 flex justify-end bg-navy-deep/40" @click.self="mode = null">
      <aside class="h-full w-full max-w-lg overflow-y-auto bg-mist p-6 shadow-2xl">
        <div class="flex items-center justify-between"><h2 class="font-display text-xl font-extrabold text-ink">{{ mode === "create" ? "新建用户" : "编辑用户" }}</h2><button class="rounded p-2 text-secondarytext hover:bg-boundary/50" @click="mode = null"><X class="h-5 w-5" /></button></div>
        <div v-if="formError" class="mt-4 rounded-md border border-danger/30 bg-danger-soft p-3 text-sm text-danger">{{ formError }}</div>
        <div class="mt-5 space-y-4">
          <label v-if="mode === 'create'" class="block"><span class="text-xs font-medium text-secondarytext">用户名</span><input v-model.trim="form.username" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm" /></label>
          <label v-if="mode === 'create'" class="block"><span class="text-xs font-medium text-secondarytext">初始密码</span><input v-model="form.password" type="password" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm" /></label>
          <label class="block"><span class="text-xs font-medium text-secondarytext">姓名</span><input v-model.trim="form.display_name" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm" /></label>
          <label class="block"><span class="text-xs font-medium text-secondarytext">业务团队</span><select v-model="form.department_id" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm"><option v-for="item in departmentOptions" :key="item.id" :value="String(item.id)">{{ item.label }}</option></select></label>
          <div><p class="text-xs font-medium text-secondarytext">角色</p><div class="mt-2 space-y-2 rounded-md border border-boundary bg-white p-3"><label v-for="role in roles" :key="role.id" class="flex items-start gap-2 text-sm"><input v-model="form.role_ids" type="checkbox" :value="role.id" class="mt-1" /><span><strong class="font-medium text-ink">{{ role.role_name }}</strong><span class="code-text ml-2 text-secondarytext">{{ role.role_code }}</span><span v-if="role.description" class="block text-xs text-secondarytext">{{ role.description }}</span></span></label></div></div>
          <label v-if="mode === 'edit'" class="block"><span class="text-xs font-medium text-secondarytext">状态</span><select v-model.number="form.status" class="mt-1 h-10 w-full rounded-md border border-boundary bg-white px-3 text-sm"><option :value="1">启用</option><option :value="0">停用</option></select></label>
        </div>
        <div class="mt-6 flex justify-end gap-2 border-t border-boundary pt-4"><button class="rounded-md border border-boundary bg-white px-4 py-2 text-sm" @click="mode = null">取消</button><button class="flex items-center gap-2 rounded-md bg-brand px-4 py-2 text-sm font-bold text-navy-deep disabled:opacity-50" :disabled="saving" @click="save"><LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" />保存</button></div>
      </aside>
    </div>
  </div>
</template>
