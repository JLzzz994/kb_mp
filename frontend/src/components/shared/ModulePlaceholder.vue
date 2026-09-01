<script setup lang="ts">
import { Construction } from "lucide-vue-next";

defineProps<{
  title: string;
  description: string;
  capability?: string;
}>();
</script>

<template>
  <section class="animate-fade-up rounded-xl border border-boundary bg-card p-8">
    <div class="flex h-12 w-12 items-center justify-center rounded-xl bg-brand-soft text-ink">
      <Construction class="h-6 w-6" aria-hidden="true" />
    </div>
    <h1 class="mt-5 font-display text-2xl font-extrabold text-ink">{{ title }}</h1>
    <p class="mt-2 max-w-2xl text-sm leading-6 text-secondarytext">{{ description }}</p>
    <p v-if="capability" class="code-text mt-5 rounded-md bg-mist px-3 py-2 text-secondarytext">
      权限：{{ capability }}
    </p>
  </section>
</template>
