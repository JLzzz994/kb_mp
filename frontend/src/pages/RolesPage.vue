<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { LoaderCircle, Save, ShieldCheck } from "lucide-vue-next";

import { ApiError } from "@/api/client";
import { assignRolePermissions, getPermissionCodes, getRoles, type RoleItem } from "@/api/org";
import PageHeader from "@/components/shared/PageHeader.vue";
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const roles = ref<RoleItem[]>([]);
const permissionCodes = ref<string[]>([]);
const selectedRoleId = ref<number | null>(null);
const selectedCodes = ref<string[]>([]);
const loading = ref(false);
const saving = ref(false);
const error = ref<string | null>(null);

const selectedRole = computed(() => roles.value.find((role) => role.id === selectedRoleId.value) ?? null);
const groups = computed(() => {
  const result = new Map<string, string[]>();
  for (const code of permissionCodes.value) {
    const prefix = code.split(":")[0] ?? "other";
    const list = result.get(prefix) ?? [];
    list.push(code);
    result.set(prefix, list);
  }
  return Array.from(result.entries()).map(([name, codes]) => ({ name, codes }));
});

function selectRole(role: RoleItem) {
  selectedRoleId.value = role.id;
  selectedCodes.value = [...role.permissions];
  error.value = null;
}

async function load() {
  loading.value = true;
  try {
    const [roleRows, codes] = await Promise.all([getRoles(), getPermissionCodes()]);
    roles.value = roleRows;
    permissionCodes.value = codes;
    if (roleRows[0]) selectRole(roleRows[0]);
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "角色权限加载失败";
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (selectedRoleId.value == null) return;
  if (!selectedCodes.value.length) {
    error.value = "后端要求角色至少保留一个权限码";
    return;
  }
  saving.value = true;
  error.value = null;
  try {
    await assignRolePermissions(selectedRoleId.value, selectedCodes.value);
    await load();
    const role = roles.value.find((item) => item.id === selectedRoleId.value);
    if (role) selectRole(role);
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : "权限保存失败";
  } finally {
    saving.value = false;
  }
}

onMounted(() => void load());
</script>

<template>
  <div class="animate-fade-up">
    <PageHeader title="角色与权限" description="后端当前支持角色列表与权限全量替换；不提供角色创建/删除接口，因此本页只做真实的权限配置。">
      <template #actions>
        <button v-if="auth.can('role:write')" class="flex h-10 items-center gap-2 rounded-md bg-brand px-4 text-sm font-bold text-navy-deep disabled:opacity-50" :disabled="saving || !selectedRole" @click="save">
          <LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" /><Save v-else class="h-4 w-4" />保存权限
        </button>
      </template>
    </PageHeader>

    <div v-if="error" class="mb-4 rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm text-danger">{{ error }}</div>
    <div v-if="loading" class="flex min-h-64 items-center justify-center text-secondarytext"><LoaderCircle class="mr-2 h-5 w-5 animate-spin" />加载中…</div>
    <div v-else class="grid gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
      <section class="rounded-xl border border-boundary bg-card p-3">
        <button v-for="role in roles" :key="role.id" class="mb-2 w-full rounded-lg border p-4 text-left transition" :class="selectedRoleId === role.id ? 'border-brand bg-brand-soft' : 'border-boundary hover:bg-mist'" @click="selectRole(role)">
          <div class="flex items-center gap-2"><ShieldCheck class="h-4 w-4 text-brand" /><strong class="text-sm text-ink">{{ role.role_name }}</strong></div>
          <p class="code-text mt-1 text-secondarytext">{{ role.role_code }}</p>
          <p class="mt-2 text-xs text-secondarytext">{{ role.description || "—" }}</p>
          <p class="mt-2 text-xs font-medium text-ink">{{ role.permissions.length }} 个权限</p>
        </button>
      </section>

      <section class="rounded-xl border border-boundary bg-card p-5">
        <template v-if="selectedRole">
          <div class="border-b border-boundary pb-4"><h2 class="font-display text-lg font-extrabold text-ink">{{ selectedRole.role_name }}</h2><p class="mt-1 text-sm text-secondarytext">保存后会替换该角色全部权限，并使持有该角色用户的 Redis 权限位图失效。</p></div>
          <div class="mt-5 grid gap-4 md:grid-cols-2">
            <fieldset v-for="group in groups" :key="group.name" class="rounded-lg border border-boundary p-4">
              <legend class="px-1 font-display text-sm font-bold uppercase text-ink">{{ group.name }}</legend>
              <label v-for="code in group.codes" :key="code" class="mt-2 flex items-center gap-2 text-sm text-primarytext">
                <input v-model="selectedCodes" type="checkbox" :value="code" :disabled="!auth.can('role:write')" />
                <span class="code-text">{{ code }}</span>
              </label>
            </fieldset>
          </div>
        </template>
        <p v-else class="py-16 text-center text-sm text-secondarytext">暂无角色</p>
      </section>
    </div>
  </div>
</template>
