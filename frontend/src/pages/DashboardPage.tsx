import { useCallback, useEffect, useState } from "react";
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { Activity, Eye, FileText, Coins, Timer, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { PageLoading, ErrorState, EmptyState } from "@/components/shared/PageStates";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  getMetrics,
  getTokenStats,
  getResponseTimeStats,
  getQuestionRankings,
  getUnitRankings,
  type StatsRange,
} from "@/api/dashboard";
import { ApiError } from "@/api/client";
import { formatNumber, formatTokens, formatMs, formatDateTime } from "@/lib/utils";

const RANGE_WHITELIST: StatsRange[] = ["7d", "30d", "90d"];

export default function DashboardPage() {
  const [range, setRange] = useState<StatsRange>("30d");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<Awaited<ReturnType<typeof getMetrics>> | null>(null);
  const [tokenStats, setTokenStats] = useState<Awaited<ReturnType<typeof getTokenStats>>>([]);
  const [rtStats, setRtStats] = useState<Awaited<ReturnType<typeof getResponseTimeStats>>>([]);
  const [questionRank, setQuestionRank] = useState<Awaited<ReturnType<typeof getQuestionRankings>>>([]);
  const [unitRank, setUnitRank] = useState<Awaited<ReturnType<typeof getUnitRankings>>>([]);

  const load = useCallback(async (r: StatsRange) => {
    setLoading(true);
    setError(null);
    try {
      const days = range === "7d" ? 7 : range === "30d" ? 30 : 90;
      const [m, t, rt, q, u] = await Promise.all([
        getMetrics(r),
        getTokenStats(Math.min(days, 30)),
        getResponseTimeStats(Math.min(days, 30)),
        getQuestionRankings(days),
        getUnitRankings(days),
      ]);
      setMetrics(m);
      setTokenStats(t);
      setRtStats(rt);
      setQuestionRank(q);
      setUnitRank(u);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "数据加载失败，请检查后端服务");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(range);
  }, [range, load]);

  if (loading && !metrics) return <PageLoading />;
  if (error && !metrics)
    return <ErrorState detail={error} onRetry={() => void load(range)} />;
  if (!metrics) return null;

  const metricCards = [
    { label: "访问次数", value: formatNumber(metrics.access_count), icon: Eye, hint: `近 ${metrics.range_days} 天` },
    { label: "独立用户（UV）", value: formatNumber(metrics.unique_users), icon: Activity, hint: `近 ${metrics.range_days} 天` },
    { label: "知识单元数", value: formatNumber(metrics.unit_count), icon: FileText, hint: "active 状态" },
    { label: "Token 总量", value: formatTokens(metrics.total_tokens), icon: Coins, hint: `近 ${metrics.range_days} 天` },
    { label: "平均响应时间", value: formatMs(metrics.avg_response_time_ms), icon: Timer, hint: "端到端" },
  ];

  return (
    <div className="animate-fade-up">
      <PageHeader
        title="数据看板"
        description="平台的知识资产、AI 使用与鉴权运行是否健康。"
        actions={
          <Tabs value={range} onValueChange={(v) => setRange(v as StatsRange)}>
            <TabsList aria-label="时间范围">
              {RANGE_WHITELIST.map((r) => (
                <TabsTrigger key={r} value={r}>
                  {r.toUpperCase()}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        }
      />

      {/* 权限脉冲线：看板标志性元素 */}
      <div className="permission-pulse-line mb-6" aria-hidden />

      <section aria-label="核心指标" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {metricCards.map((m) => (
          <Card key={m.label} className="border-boundary">
            <CardContent className="py-5">
              <div className="flex items-center justify-between">
                <p className="text-[13px] font-medium text-secondarytext">{m.label}</p>
                <m.icon className="h-4 w-4 text-brand" aria-hidden />
              </div>
              <p className="metric-number mt-2 text-ink">{m.value}</p>
              <p className="mt-1 text-xs text-secondarytext/70">{m.hint}</p>
            </CardContent>
          </Card>
        ))}
      </section>

      <section aria-label="趋势" className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card className="border-boundary">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <TrendingUp className="h-4 w-4 text-brand" aria-hidden /> Token 消耗趋势
            </CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            {tokenStats.length === 0 ? (
              <EmptyState title="暂无 Token 数据" description="发起 AI 问答后此处将展示消耗趋势" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={tokenStats} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <defs>
                    <linearGradient id="tokenFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#36C2A4" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#36C2A4" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#DCE6ED" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="bucket_date"
                    tick={{ fill: "#6E8190", fontSize: 12 }}
                    tickLine={false}
                    axisLine={{ stroke: "#DCE6ED" }}
                  />
                  <YAxis tick={{ fill: "#6E8190", fontSize: 12 }} tickLine={false} axisLine={false} width={48} />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 8,
                      border: "1px solid #DCE6ED",
                      fontSize: 13,
                    }}
                    formatter={(v: number | string) => [formatNumber(Number(v)), "Token"]}
                  />
                  <Area
                    type="monotone"
                    dataKey="total_tokens"
                    stroke="#36C2A4"
                    strokeWidth={2}
                    fill="url(#tokenFill)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card className="border-boundary">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Timer className="h-4 w-4 text-review" aria-hidden /> 响应时间趋势（均值 / P95）
            </CardTitle>
          </CardHeader>
          <CardContent className="h-64">
            {rtStats.length === 0 ? (
              <EmptyState title="暂无响应时间数据" description="发起 AI 问答后此处将展示耗时趋势" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={rtStats} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="#DCE6ED" strokeDasharray="3 3" vertical={false} />
                  <XAxis
                    dataKey="bucket_date"
                    tick={{ fill: "#6E8190", fontSize: 12 }}
                    tickLine={false}
                    axisLine={{ stroke: "#DCE6ED" }}
                  />
                  <YAxis
                    tick={{ fill: "#6E8190", fontSize: 12 }}
                    tickLine={false}
                    axisLine={false}
                    width={48}
                    tickFormatter={(v: number) => `${Math.round(v / 100) / 10}s`}
                  />
                  <Tooltip
                    contentStyle={{ borderRadius: 8, border: "1px solid #DCE6ED", fontSize: 13 }}
                    formatter={(v: number | string, name: string) => [formatMs(Number(v)), name]}
                  />
                  <Line type="monotone" dataKey="avg_response_time_ms" stroke="#18354D" strokeWidth={2} dot={false} name="均值" />
                  <Line type="monotone" dataKey="p95_response_time_ms" stroke="#F2A65A" strokeWidth={2} dot={false} name="P95" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </section>

      <section aria-label="排行榜" className="mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <Card className="border-boundary">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">高频问题 TOP</CardTitle>
          </CardHeader>
          <CardContent>
            {questionRank.length === 0 ? (
              <EmptyState title="暂无问答记录" />
            ) : (
              <ol className="divide-y divide-boundary">
                {questionRank.slice(0, 10).map((q, i) => (
                  <li key={q.question} className="flex items-center gap-3 py-2.5">
                    <span className="code-text w-6 shrink-0 text-right font-medium text-secondarytext">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-primarytext" title={q.question}>
                      {q.question}
                    </span>
                    <span className="shrink-0 rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-semibold text-ink">
                      {q.ask_count} 次
                    </span>
                    <span className="hidden shrink-0 text-xs text-secondarytext sm:block">
                      {formatDateTime(q.last_asked_at)}
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>

        <Card className="border-boundary">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">知识热度 TOP</CardTitle>
          </CardHeader>
          <CardContent>
            {unitRank.length === 0 ? (
              <EmptyState title="暂无知识单元访问" />
            ) : (
              <ol className="divide-y divide-boundary">
                {unitRank.slice(0, 10).map((u, i) => (
                  <li key={u.unit_id} className="flex items-center gap-3 py-2.5">
                    <span className="code-text w-6 shrink-0 text-right font-medium text-secondarytext">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-primarytext" title={u.title}>
                      {u.title}
                    </span>
                    <span className="code-text hidden shrink-0 text-xs text-secondarytext md:block">
                      {u.unit_code}
                    </span>
                    <span className="shrink-0 rounded-full bg-review-soft px-2.5 py-0.5 text-xs font-semibold text-ink">
                      {u.access_count} 次
                    </span>
                  </li>
                ))}
              </ol>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
