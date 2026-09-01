<script setup lang="ts">
import { useAuthStore } from "@/stores/auth";
import PageHeader from "@/components/shared/PageHeader.vue";

const auth = useAuthStore();
</script>

<template>
  <div class="animate-fade-up">
    <PageHeader title="个人信息" description="当前登录身份与权限上下文。" />
    <section class="rounded-xl border border-boundary bg-card p-6">
      <dl class="grid gap-4 sm:grid-cols-2">
        <div>
          <dt class="text-xs text-secondarytext">姓名</dt>
          <dd class="mt-1 font-medium text-ink">{{ auth.user?.display_name ?? "—" }}</dd>
        </div>
        <div>
          <dt class="text-xs text-secondarytext">用户名</dt>
          <dd class="code-text mt-1 text-ink">{{ auth.user?.username ?? "—" }}</dd>
        </div>
        <div>
          <dt class="text-xs text-secondarytext">部门</dt>
          <dd class="mt-1 text-ink">{{ auth.user?.department_name ?? "—" }}</dd>
        </div>
        <div>
          <dt class="text-xs text-secondarytext">角色</dt>
          <dd class="mt-1 text-ink">{{ auth.user?.role_codes?.join(" · ") || "—" }}</dd>
        </div>
      </dl>
    </section>
  </div>
</template>
