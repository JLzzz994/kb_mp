<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import {
  BookOpen,
  Building2,
  CircleHelp,
  FileUp,
  LayoutDashboard,
  LogOut,
  Menu,
  MessagesSquare,
  ShieldCheck,
  Target,
  Users,
  X,
} from "lucide-vue-next";

import { useAuthStore } from "@/stores/auth";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const drawerOpen = ref(false);

const navItems = [
  { to: "/", label: "知识运营看板", icon: LayoutDashboard, permission: "dashboard:read" },
  { to: "/users", label: "用户管理", icon: Users, permission: "user:read" },
  { to: "/roles", label: "角色与权限", icon: ShieldCheck, permission: "role:read" },
  { to: "/departments", label: "业务团队", icon: Building2, permission: "dept:read" },
  { to: "/knowledge/import", label: "产品文档导入", icon: FileUp, permission: "knowledge:write" },
  { to: "/knowledge/units", label: "知识资产", icon: BookOpen, permission: "knowledge:read" },
  { to: "/chat", label: "ERP/WMS 智能问答", icon: MessagesSquare, permission: "ai:chat" },
  { to: "/faqs", label: "FAQ 审核", icon: CircleHelp, permission: "faq:read" },
  { to: "/gaps", label: "知识缺口", icon: Target, permission: "gap:read" },
] as const;

const visibleItems = computed(() =>
  navItems.filter((item) => auth.permissions.includes(item.permission)),
);

function activePath(path: string): boolean {
  return path === "/" ? route.path === "/" : route.path.startsWith(path);
}

async function handleLogout() {
  auth.clearSession();
  await router.replace("/login");
}
</script>

<template>
  <div class="flex min-h-screen">
    <aside class="sticky top-0 hidden h-screen w-60 shrink-0 lg:block">
      <nav class="flex h-full flex-col bg-navy text-white/90" aria-label="主导航">
        <div class="flex items-center gap-2.5 px-5 py-5">
          <span class="flex h-9 w-9 items-center justify-center rounded-lg bg-brand font-display text-lg font-extrabold text-navy-deep">
            慧
          </span>
          <div>
            <p class="font-display text-[15px] font-extrabold tracking-tight text-white">
              ERP/WMS 产品知识运营
            </p>
            <p class="text-xs text-white/50">Vue 3 · Huice Knowledge Ops</p>
          </div>
        </div>
        <div class="mx-5 h-px bg-white/10" />
        <ul class="thin-scrollbar flex-1 space-y-1 overflow-y-auto px-3 py-4">
          <li v-for="item in visibleItems" :key="item.to">
            <RouterLink
              :to="item.to"
              class="flex min-h-[44px] items-center gap-3 rounded-md px-3 text-sm font-medium transition-colors"
              :class="
                activePath(item.to)
                  ? 'bg-white/10 text-white shadow-[inset_2px_0_0_0_#36C2A4]'
                  : 'text-white/60 hover:bg-white/5 hover:text-white'
              "
            >
              <component :is="item.icon" class="h-[18px] w-[18px] shrink-0" aria-hidden="true" />
              {{ item.label }}
            </RouterLink>
          </li>
        </ul>
        <div class="border-t border-white/10 p-4">
          <div class="flex items-center gap-3">
            <span class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/10 font-display text-sm font-bold text-brand">
              {{ auth.user?.display_name?.slice(0, 1) ?? "?" }}
            </span>
            <div class="min-w-0 flex-1">
              <p class="truncate text-sm font-medium text-white">
                {{ auth.user?.display_name ?? "未知用户" }}
              </p>
              <p class="code-text truncate text-white/45">
                {{ auth.user?.role_codes?.join(" · ") || auth.user?.username }}
              </p>
            </div>
            <button
              class="flex h-11 w-11 items-center justify-center rounded-md text-white/60 hover:bg-white/10 hover:text-white"
              aria-label="退出登录"
              title="退出登录"
              @click="handleLogout"
            >
              <LogOut class="h-[18px] w-[18px]" aria-hidden="true" />
            </button>
          </div>
        </div>
      </nav>
    </aside>

    <div v-if="drawerOpen" class="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
      <button class="absolute inset-0 bg-navy-deep/60" aria-label="关闭导航" @click="drawerOpen = false" />
      <div class="absolute inset-y-0 left-0 w-64 bg-navy shadow-2xl">
        <button
          class="absolute right-3 top-4 z-10 flex h-11 w-11 items-center justify-center rounded-md text-white/70 hover:bg-white/10"
          aria-label="关闭导航"
          @click="drawerOpen = false"
        >
          <X class="h-5 w-5" aria-hidden="true" />
        </button>
        <div class="px-5 py-5 font-display font-extrabold text-white">ERP/WMS 产品知识运营</div>
        <ul class="space-y-1 px-3 py-4">
          <li v-for="item in visibleItems" :key="item.to">
            <RouterLink
              :to="item.to"
              class="flex min-h-[44px] items-center gap-3 rounded-md px-3 text-sm"
              :class="activePath(item.to) ? 'bg-white/10 text-white' : 'text-white/60'"
              @click="drawerOpen = false"
            >
              <component :is="item.icon" class="h-[18px] w-[18px]" aria-hidden="true" />
              {{ item.label }}
            </RouterLink>
          </li>
        </ul>
      </div>
    </div>

    <div class="flex min-w-0 flex-1 flex-col">
      <div class="sticky top-0 z-40 flex items-center gap-3 border-b border-boundary bg-mist/90 px-4 py-3 backdrop-blur lg:hidden">
        <button
          class="flex h-11 w-11 items-center justify-center rounded-md text-ink hover:bg-boundary/50"
          aria-label="打开导航"
          @click="drawerOpen = true"
        >
          <Menu class="h-5 w-5" aria-hidden="true" />
        </button>
        <span class="font-display font-extrabold text-ink">ERP/WMS 产品知识运营平台</span>
      </div>
      <main class="mx-auto w-full max-w-[1280px] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <RouterView />
      </main>
    </div>
  </div>
</template>
