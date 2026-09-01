<script setup lang="ts">
import { computed, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { AlertCircle, LoaderCircle, ShieldCheck } from "lucide-vue-next";

import { login } from "@/api/auth";
import { ApiError } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

const form = reactive({ username: "", password: "" });
const submitting = ref(false);
const serverError = ref<string | null>(null);

const usernameError = computed(() => {
  if (!form.username) return "请输入用户名";
  if (form.username.length < 3) return "用户名至少 3 个字符";
  if (form.username.length > 64) return "用户名最多 64 个字符";
  if (!/^[a-zA-Z0-9_]+$/.test(form.username)) return "仅支持字母、数字与下划线";
  return "";
});

const passwordError = computed(() => {
  if (!form.password) return "请输入密码";
  if (form.password.length < 6) return "密码至少 6 位";
  if (form.password.length > 128) return "密码最多 128 位";
  return "";
});

async function submit() {
  serverError.value = null;
  if (usernameError.value || passwordError.value) return;
  submitting.value = true;
  try {
    const response = await login(form.username, form.password);
    auth.setSession(response.user_info, response.permissions);
    const redirect = typeof route.query.redirect === "string" ? route.query.redirect : "/";
    await router.replace(redirect.startsWith("/") ? redirect : "/");
  } catch (error) {
    if (error instanceof ApiError) {
      serverError.value =
        error.status === 401
          ? "用户名或密码错误，或账号已被停用"
          : `登录失败：${error.message}`;
    } else {
      serverError.value = "网络异常，请稍后重试";
    }
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center px-4 py-10">
    <div class="grid w-full max-w-4xl overflow-hidden rounded-2xl border border-boundary bg-card shadow-xl shadow-ink/5 md:grid-cols-[1.05fr_1fr]">
      <section class="relative hidden flex-col justify-between bg-navy p-10 text-white md:flex">
        <div>
          <p class="code-text text-brand">HUICE · ERP/WMS · VUE 3</p>
          <h1 class="mt-4 font-display text-[32px] font-extrabold leading-tight tracking-tight">
            产品知识运营平台<br />权限可控的 RAG 问答
          </h1>
          <p class="mt-4 max-w-xs text-sm leading-relaxed text-white/60">
            MinerU 结构化解析 · 混合检索 · 权限过滤 · FAQ 审核 · 知识缺口 · 引用追溯
          </p>
        </div>
        <div class="mt-10">
          <div class="permission-pulse-line" aria-hidden="true" />
          <div class="mt-4 flex items-center gap-2 text-xs text-white/50">
            <ShieldCheck class="h-4 w-4 text-brand" aria-hidden="true" />
            面向产品、实施、客服和客户成功团队，召回后先鉴权再回答
          </div>
        </div>
      </section>

      <section class="p-8 sm:p-10">
        <h2 class="font-display text-2xl font-extrabold tracking-tight text-ink">登录</h2>
        <p class="mt-1.5 text-sm text-secondarytext">进入 ERP/WMS 产品知识运营管理台</p>

        <div
          v-if="serverError"
          role="alert"
          class="mt-5 flex items-start gap-2.5 rounded-md border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger"
        >
          <AlertCircle class="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {{ serverError }}
        </div>

        <form class="mt-6 space-y-5" novalidate @submit.prevent="submit">
          <div class="space-y-2">
            <label class="text-sm font-medium text-ink" for="username">用户名</label>
            <input
              id="username"
              v-model.trim="form.username"
              autocomplete="username"
              placeholder="admin"
              class="h-11 w-full rounded-md border border-boundary bg-white px-3 text-sm outline-none focus:border-brand"
            />
            <p v-if="form.username && usernameError" class="text-[13px] text-danger">
              {{ usernameError }}
            </p>
          </div>
          <div class="space-y-2">
            <label class="text-sm font-medium text-ink" for="password">密码</label>
            <input
              id="password"
              v-model="form.password"
              type="password"
              autocomplete="current-password"
              placeholder="••••••••"
              class="h-11 w-full rounded-md border border-boundary bg-white px-3 text-sm outline-none focus:border-brand"
            />
            <p v-if="form.password && passwordError" class="text-[13px] text-danger">
              {{ passwordError }}
            </p>
          </div>
          <button
            type="submit"
            :disabled="submitting"
            class="flex h-11 w-full items-center justify-center gap-2 rounded-md bg-brand px-4 text-sm font-bold text-navy-deep transition hover:brightness-95 disabled:opacity-50"
          >
            <LoaderCircle v-if="submitting" class="h-4 w-4 animate-spin" aria-hidden="true" />
            {{ submitting ? "登录中…" : "登 录" }}
          </button>
        </form>
        <p class="mt-6 text-xs leading-relaxed text-secondarytext">
          演示账号：admin（平台管理员）/ kadmin（产品知识管理员）/ alice（实施顾问），密码见 seed 数据。
        </p>
      </section>
    </div>
  </div>
</template>
