<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import * as echarts from "echarts";
import { Activity, BookOpen, Gauge, MessageSquareText, Timer, Users } from "lucide-vue-next";

import {
  getMetrics,
  getQuestionRankings,
  getResponseTimeStats,
  getTokenStats,
  getUnitRankings,
  type MetricsResponse,
  type QuestionRankingItem,
  type ResponseTimeStatsBucket,
  type StatsRange,
  type TokenStatsBucket,
  type UnitRankingItem,
} from "@/api/dashboard";
import PageHeader from "@/components/shared/PageHeader.vue";
import { formatDateTime, formatMs, formatNumber, formatTokens } from "@/lib/utils";

const range = ref<StatsRange>("7d");
const loading = ref(false);
const error = ref<string | null>(null);
const metrics = ref<MetricsResponse | null>(null);
const questionRank = ref<QuestionRankingItem[]>([]);
const unitRank = ref<UnitRankingItem[]>([]);
const tokenStats = ref<TokenStatsBucket[]>([]);
const responseStats = ref<ResponseTimeStatsBucket[]>([]);

const tokenEl = ref<HTMLDivElement | null>(null);
const responseEl = ref<HTMLDivElement | null>(null);
let tokenChart: echarts.ECharts | null = null;
let responseChart: echarts.ECharts | null = null;

async function load() {
  loading.value = true;
  error.value = null;
  const days = range.value === "7d" ? 7 : range.value === "30d" ? 30 : 90;
  try {
    const [m, q, u, tokens, responses] = await Promise.all([
      getMetrics(range.value),
      getQuestionRankings(days),
      getUnitRankings(days),
      getTokenStats(days),
      getResponseTimeStats(days),
    ]);
    metrics.value = m;
    questionRank.value = q;
    unitRank.value = u;
    tokenStats.value = tokens;
    responseStats.value = responses;
    await nextTick();
    renderCharts();
  } catch {
    error.value = "看板数据加载失败，请确认 dashboard 权限与后端服务状态。";
  } finally {
    loading.value = false;
  }
}

function renderCharts() {
  if (tokenEl.value) {
    tokenChart ??= echarts.init(tokenEl.value);
    tokenChart.setOption({
      tooltip: { trigger: "axis" },
      grid: { left: 52, right: 18, top: 20, bottom: 34 },
      xAxis: {
        type: "category",
        data: tokenStats.value.map((item) => item.bucket_date),
        axisLabel: { color: "#6E8190" },
        axisLine: { lineStyle: { color: "#DCE6ED" } },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#6E8190" },
        splitLine: { lineStyle: { color: "#EDF2F7" } },
      },
      series: [
        {
          name: "Token",
          type: "line",
          smooth: true,
          symbol: "none",
          areaStyle: { opacity: 0.16 },
          lineStyle: { width: 2 },
          data: tokenStats.value.map((item) => item.total_tokens),
        },
      ],
    });
  }

  if (responseEl.value) {
    responseChart ??= echarts.init(responseEl.value);
    responseChart.setOption({
      tooltip: { trigger: "axis", valueFormatter: (value) => formatMs(Number(value)) },
      legend: { data: ["均值", "P95"], right: 8 },
      grid: { left: 52, right: 18, top: 42, bottom: 34 },
      xAxis: {
        type: "category",
        data: responseStats.value.map((item) => item.bucket_date),
        axisLabel: { color: "#6E8190" },
        axisLine: { lineStyle: { color: "#DCE6ED" } },
      },
      yAxis: {
        type: "value",
        axisLabel: { color: "#6E8190", formatter: (value: number) => formatMs(value) },
        splitLine: { lineStyle: { color: "#EDF2F7" } },
      },
      series: [
        {
          name: "均值",
          type: "line",
          smooth: true,
          symbol: "none",
          data: responseStats.value.map((item) => item.avg_response_time_ms),
        },
        {
          name: "P95",
          type: "line",
          smooth: true,
          symbol: "none",
          data: responseStats.value.map((item) => item.p95_response_time_ms),
        },
      ],
    });
  }
}

function resizeCharts() {
  tokenChart?.resize();
  responseChart?.resize();
}

watch(range, () => void load());

onMounted(() => {
  void load();
  window.addEventListener("resize", resizeCharts);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", resizeCharts);
  tokenChart?.dispose();
  responseChart?.dispose();
});
</script>

<template>
  <div class="animate-fade-up">
    <PageHeader
      title="知识运营看板"
      description="观察 ERP/WMS 产品知识访问、AI 问答消耗、响应性能与高频知识热点。"
    >
      <template #actions>
        <select v-model="range" class="h-10 rounded-md border border-boundary bg-white px-3 text-sm text-ink">
          <option value="7d">近 7 天</option>
          <option value="30d">近 30 天</option>
          <option value="90d">近 90 天</option>
        </select>
      </template>
    </PageHeader>

    <div v-if="error" class="mb-5 rounded-lg border border-danger/30 bg-danger-soft p-4 text-sm text-danger">
      {{ error }}
    </div>

    <section class="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
      <article v-for="card in [
        { label: '知识访问', value: formatNumber(metrics?.access_count), icon: Activity },
        { label: '活跃用户', value: formatNumber(metrics?.unique_users), icon: Users },
        { label: '产品知识单元', value: formatNumber(metrics?.unit_count), icon: BookOpen },
        { label: 'Token 消耗', value: formatTokens(metrics?.total_tokens), icon: MessageSquareText },
        { label: '平均响应', value: formatMs(metrics?.avg_response_time_ms), icon: Gauge },
      ]" :key="card.label" class="rounded-xl border border-boundary bg-card p-5">
        <div class="flex items-center justify-between">
          <p class="text-sm text-secondarytext">{{ card.label }}</p>
          <component :is="card.icon" class="h-4 w-4 text-brand" aria-hidden="true" />
        </div>
        <p class="metric-number mt-3 text-ink">{{ loading ? "…" : card.value }}</p>
      </article>
    </section>

    <section class="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
      <article class="rounded-xl border border-boundary bg-card p-5">
        <h2 class="flex items-center gap-2 font-display font-bold text-ink">
          <Activity class="h-4 w-4 text-brand" aria-hidden="true" /> Token 消耗趋势 · ECharts
        </h2>
        <div ref="tokenEl" class="mt-3 h-64 w-full" />
      </article>
      <article class="rounded-xl border border-boundary bg-card p-5">
        <h2 class="flex items-center gap-2 font-display font-bold text-ink">
          <Timer class="h-4 w-4 text-review" aria-hidden="true" /> 响应时间趋势（均值 / P95）
        </h2>
        <div ref="responseEl" class="mt-3 h-64 w-full" />
      </article>
    </section>

    <section class="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
      <article class="rounded-xl border border-boundary bg-card p-5">
        <h2 class="font-display font-bold text-ink">高频问题 TOP</h2>
        <p v-if="!questionRank.length" class="py-8 text-center text-sm text-secondarytext">暂无问答记录</p>
        <ol v-else class="mt-3 divide-y divide-boundary">
          <li v-for="(item, index) in questionRank.slice(0, 10)" :key="item.question" class="flex items-center gap-3 py-2.5">
            <span class="code-text w-6 text-right text-secondarytext">{{ String(index + 1).padStart(2, "0") }}</span>
            <span class="min-w-0 flex-1 truncate text-sm text-primarytext" :title="item.question">{{ item.question }}</span>
            <span class="rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-semibold text-ink">{{ item.ask_count }} 次</span>
            <span class="hidden text-xs text-secondarytext sm:block">{{ formatDateTime(item.last_asked_at) }}</span>
          </li>
        </ol>
      </article>

      <article class="rounded-xl border border-boundary bg-card p-5">
        <h2 class="font-display font-bold text-ink">产品知识热度 TOP</h2>
        <p v-if="!unitRank.length" class="py-8 text-center text-sm text-secondarytext">暂无知识访问记录</p>
        <ol v-else class="mt-3 divide-y divide-boundary">
          <li v-for="(item, index) in unitRank.slice(0, 10)" :key="item.unit_id" class="flex items-center gap-3 py-2.5">
            <span class="code-text w-6 text-right text-secondarytext">{{ String(index + 1).padStart(2, "0") }}</span>
            <span class="min-w-0 flex-1 truncate text-sm text-primarytext" :title="item.title">{{ item.title }}</span>
            <span class="code-text hidden text-xs text-secondarytext md:block">{{ item.unit_code }}</span>
            <span class="rounded-full bg-review-soft px-2.5 py-0.5 text-xs font-semibold text-ink">{{ item.access_count }} 次</span>
          </li>
        </ol>
      </article>
    </section>
  </div>
</template>
