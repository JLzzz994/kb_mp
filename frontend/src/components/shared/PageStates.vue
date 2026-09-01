<script setup lang="ts">
import { LoaderCircle } from "lucide-vue-next";

withDefaults(
  defineProps<{
    loading?: boolean;
    error?: string | null;
    empty?: boolean;
    emptyTitle?: string;
  }>(),
  { loading: false, error: null, empty: false, emptyTitle: "暂无数据" },
);
</script>

<template>
  <div v-if="loading" class="flex min-h-40 items-center justify-center text-secondarytext">
    <LoaderCircle class="mr-2 h-5 w-5 animate-spin" aria-hidden="true" />
    加载中…
  </div>
  <div v-else-if="error" class="rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm text-danger">
    {{ error }}
  </div>
  <div v-else-if="empty" class="py-10 text-center text-sm text-secondarytext">
    {{ emptyTitle }}
  </div>
  <slot v-else />
</template>
