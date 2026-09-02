<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { Globe2, LoaderCircle, Save, ShieldCheck, Users } from "lucide-vue-next";

import { ApiError } from "@/api/client";
import {
  configureUnitPermissions,
  type PermissionEntry,
} from "@/api/knowledge";
import {
  getDepartments,
  getRoles,
  getUsers,
  type DepartmentNode,
  type RoleItem,
  type UserItem,
} from "@/api/org";

const props = defineProps<{
  unitId: number;
  permissions: PermissionEntry[];
}>();

const emit = defineEmits<{
  saved: [permissions: PermissionEntry[]];
}>();

type Mode = "global" | "scoped";

interface DepartmentOption {
  id: number;
  label: string;
}

const mode = ref<Mode>("scoped");
const selectedDepartments = ref<number[]>([]);
const selectedRoles = ref<number[]>([]);
const selectedUsers = ref<number[]>([]);
const departments = ref<DepartmentNode[]>([]);
const roles = ref<RoleItem[]>([]);
const users = ref<UserItem[]>([]);
const userKeyword = ref("");
const loadingOptions = ref(false);
const saving = ref(false);
const error = ref<string | null>(null);

function flattenDepartments(nodes: DepartmentNode[], depth = 0): DepartmentOption[] {
  return nodes.flatMap((node) => [
    { id: node.id, label: "—".repeat(depth) + (depth ? " " : "") + node.name },
    ...flattenDepartments(node.children, depth + 1),
  ]);
}

const departmentOptions = computed(() => flattenDepartments(departments.value));
const visibleUsers = computed(() => {
  const keyword = userKeyword.value.trim().toLowerCase();
  if (!keyword) return users.value;
  return users.value.filter(
    (user) =>
      user.display_name.toLowerCase().includes(keyword) ||
      user.username.toLowerCase().includes(keyword),
  );
});
const scopedCount = computed(
  () =>
    selectedDepartments.value.length +
    selectedRoles.value.length +
    selectedUsers.value.length,
);

function resetFromPermissions() {
  const hasGlobal = props.permissions.some((item) => item.target_type === "global");
  mode.value = hasGlobal ? "global" : "scoped";
  selectedDepartments.value = props.permissions
    .filter((item) => item.target_type === "department" && item.target_id != null)
    .map((item) => Number(item.target_id));
  selectedRoles.value = props.permissions
    .filter((item) => item.target_type === "role" && item.target_id != null)
    .map((item) => Number(item.target_id));
  selectedUsers.value = props.permissions
    .filter((item) => item.target_type === "user" && item.target_id != null)
    .map((item) => Number(item.target_id));
}

watch(() => props.permissions, resetFromPermissions, { deep: true, immediate: true });

async function loadOptions() {
  loadingOptions.value = true;
  error.value = null;
  try {
    const [departmentRows, roleRows, userPage] = await Promise.all([
      getDepartments(),
      getRoles(),
      getUsers({ page: 1, page_size: 200, status: 1 }),
    ]);
    departments.value = departmentRows;
    roles.value = roleRows;
    users.value = userPage.items;
  } catch (err) {
    error.value =
      err instanceof ApiError
        ? `授权目标加载失败：${err.message}`
        : "授权目标加载失败";
  } finally {
    loadingOptions.value = false;
  }
}

async function save() {
  error.value = null;
  const entries =
    mode.value === "global"
      ? [{ target_type: "global" as const, target_id: null }]
      : [
          ...selectedDepartments.value.map((id) => ({
            target_type: "department" as const,
            target_id: id,
          })),
          ...selectedRoles.value.map((id) => ({
            target_type: "role" as const,
            target_id: id,
          })),
          ...selectedUsers.value.map((id) => ({
            target_type: "user" as const,
            target_id: id,
          })),
        ];

  if (!entries.length) {
    error.value = "范围授权至少选择一个部门、角色或用户";
    return;
  }

  saving.value = true;
  try {
    const resolved = await configureUnitPermissions(props.unitId, entries);
    emit("saved", resolved);
  } catch (err) {
    error.value =
      err instanceof ApiError ? `权限保存失败：${err.message}` : "权限保存失败";
  } finally {
    saving.value = false;
  }
}

onMounted(() => void loadOptions());
</script>

<template>
  <section class="rounded-xl border border-boundary bg-card p-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="flex items-center gap-2 font-display text-sm font-bold text-ink">
          <ShieldCheck class="h-4 w-4 text-brand" />
          四维知识权限
        </p>
        <p class="mt-1 text-xs leading-5 text-secondarytext">
          global 与范围授权互斥；department / role / user 之间采用 OR，只要命中任一维度即可访问。
        </p>
      </div>
      <button
        class="flex items-center gap-2 rounded-md bg-brand px-3 py-2 text-xs font-bold text-navy-deep disabled:opacity-50"
        :disabled="saving || loadingOptions"
        @click="save"
      >
        <LoaderCircle v-if="saving" class="h-3.5 w-3.5 animate-spin" />
        <Save v-else class="h-3.5 w-3.5" />
        保存权限
      </button>
    </div>

    <div
      v-if="error"
      class="mt-3 rounded-md border border-danger/30 bg-danger-soft p-3 text-xs text-danger"
    >
      {{ error }}
    </div>

    <div class="mt-4 grid gap-3 sm:grid-cols-2">
      <label
        class="cursor-pointer rounded-lg border p-4"
        :class="mode === 'global' ? 'border-brand bg-brand-soft' : 'border-boundary'"
      >
        <div class="flex items-start gap-3">
          <input v-model="mode" type="radio" value="global" class="mt-1" />
          <div>
            <p class="flex items-center gap-2 text-sm font-bold text-ink">
              <Globe2 class="h-4 w-4" />全局公开
            </p>
            <p class="mt-1 text-xs text-secondarytext">所有已登录业务用户均可访问；不能与其他维度混用。</p>
          </div>
        </div>
      </label>
      <label
        class="cursor-pointer rounded-lg border p-4"
        :class="mode === 'scoped' ? 'border-brand bg-brand-soft' : 'border-boundary'"
      >
        <div class="flex items-start gap-3">
          <input v-model="mode" type="radio" value="scoped" class="mt-1" />
          <div>
            <p class="flex items-center gap-2 text-sm font-bold text-ink">
              <Users class="h-4 w-4" />范围授权
            </p>
            <p class="mt-1 text-xs text-secondarytext">按部门、角色、用户组合授权；当前选择 {{ scopedCount }} 项。</p>
          </div>
        </div>
      </label>
    </div>

    <div v-if="mode === 'global'" class="mt-4 rounded-md bg-review-soft p-3 text-xs leading-5 text-primarytext">
      选择全局公开后，保存请求只会包含一条 global 权限。后端也会拒绝 global 与其他维度混配。
    </div>

    <div v-else class="mt-4">
      <div v-if="loadingOptions" class="flex min-h-28 items-center justify-center text-sm text-secondarytext">
        <LoaderCircle class="mr-2 h-4 w-4 animate-spin" />加载授权目标…
      </div>
      <div v-else class="grid gap-4 xl:grid-cols-3">
        <fieldset class="rounded-lg border border-boundary bg-mist/50 p-3">
          <legend class="px-1 text-xs font-bold text-ink">部门</legend>
          <div class="thin-scrollbar mt-2 max-h-52 space-y-2 overflow-y-auto">
            <label v-for="item in departmentOptions" :key="item.id" class="flex items-center gap-2 text-xs text-primarytext">
              <input v-model="selectedDepartments" type="checkbox" :value="item.id" />
              <span>{{ item.label }}</span>
            </label>
            <p v-if="!departmentOptions.length" class="text-xs text-secondarytext">暂无部门</p>
          </div>
        </fieldset>

        <fieldset class="rounded-lg border border-boundary bg-mist/50 p-3">
          <legend class="px-1 text-xs font-bold text-ink">角色</legend>
          <div class="thin-scrollbar mt-2 max-h-52 space-y-2 overflow-y-auto">
            <label v-for="role in roles" :key="role.id" class="flex items-center gap-2 text-xs text-primarytext">
              <input v-model="selectedRoles" type="checkbox" :value="role.id" />
              <span>{{ role.role_name }} <span class="code-text text-secondarytext">{{ role.role_code }}</span></span>
            </label>
            <p v-if="!roles.length" class="text-xs text-secondarytext">暂无角色</p>
          </div>
        </fieldset>

        <fieldset class="rounded-lg border border-boundary bg-mist/50 p-3">
          <legend class="px-1 text-xs font-bold text-ink">用户</legend>
          <input
            v-model.trim="userKeyword"
            class="mt-2 h-8 w-full rounded border border-boundary bg-white px-2 text-xs"
            placeholder="搜索姓名 / 用户名"
          />
          <div class="thin-scrollbar mt-2 max-h-44 space-y-2 overflow-y-auto">
            <label v-for="user in visibleUsers" :key="user.id" class="flex items-center gap-2 text-xs text-primarytext">
              <input v-model="selectedUsers" type="checkbox" :value="user.id" />
              <span>{{ user.display_name }} <span class="code-text text-secondarytext">{{ user.username }}</span></span>
            </label>
            <p v-if="!visibleUsers.length" class="text-xs text-secondarytext">暂无匹配用户</p>
          </div>
        </fieldset>
      </div>
    </div>
  </section>
</template>
