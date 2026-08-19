import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search, Trash2, ChevronLeft, ChevronRight, AlertTriangle } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { PageLoading, ErrorState, EmptyState } from "@/components/shared/PageStates";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getKnowledgeUnits, batchDeleteUnits, type KnowledgeUnitItem } from "@/api/knowledge";
import { ApiError, type PageData } from "@/api/client";
import { formatDateTime } from "@/lib/utils";
import { usePermission } from "@/auth/AuthContext";

const STATUS_OPTIONS = [
  { value: "all", label: "全部状态" },
  { value: "active", label: "已生效" },
  { value: "vector_pending", label: "向量化待重试" },
  { value: "failed", label: "解析失败" },
] as const;

const PAGE_SIZE = 20;
const BATCH_DELETE_LIMIT = 100; // 接口约定文档 §7.3：ids 1–100（从严控制）

function StatusBadge({ status }: { status: KnowledgeUnitItem["status"] }) {
  const map = {
    active: { label: "已生效", cls: "bg-brand-soft text-ink" },
    vector_pending: { label: "向量化待重试", cls: "bg-review-soft text-ink" },
    failed: { label: "解析失败", cls: "bg-danger-soft text-danger" },
  } as const;
  const s = map[status];
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${s.cls}`}>{s.label}</span>;
}

export default function KnowledgeUnitsPage() {
  const navigate = useNavigate();
  const can = usePermission();
  const canDelete = can("knowledge:delete");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<PageData<KnowledgeUnitItem> | null>(null);

  // 筛选状态（错误时保留用户输入，不清空）
  const [keyword, setKeyword] = useState("");
  const [status, setStatus] = useState<string>("all");
  const [page, setPage] = useState(1);

  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteResult, setDeleteResult] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await getKnowledgeUnits({
        page,
        page_size: PAGE_SIZE,
        keyword: keyword || undefined,
        status: status === "all" ? undefined : status,
      });
      setData(resp);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "加载失败，请检查后端服务");
    } finally {
      setLoading(false);
    }
  }, [page, keyword, status]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const allOnPageSelected =
    Boolean(data?.items.length) && data!.items.every((u) => selectedIds.includes(u.id));
  const overLimit = selectedIds.length > BATCH_DELETE_LIMIT;

  const toggleAll = () => {
    if (!data) return;
    setSelectedIds(
      allOnPageSelected ? [] : Array.from(new Set([...selectedIds, ...data.items.map((u) => u.id)])).slice(0, BATCH_DELETE_LIMIT),
    );
  };

  const toggleOne = (id: number) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handleDelete = async () => {
    setDeleting(true);
    setDeleteResult(null);
    try {
      const result = await batchDeleteUnits(selectedIds);
      if (result.failed?.length) {
        setDeleteResult(
          `部分失败：成功 ${result.succeeded.length} 条，失败 ${result.failed.length} 条（${result.failed
            .map((f) => `#${f.id} ${f.error_code}`)
            .join("、")}）`,
        );
      } else {
        setConfirmOpen(false);
        setSelectedIds([]);
        await load();
      }
    } catch (err) {
      setDeleteResult(err instanceof ApiError ? `删除失败：${err.message}` : "删除失败，请重试");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="animate-fade-up">
      <PageHeader
        title="知识单元"
        description="查找并维护具体知识单元：编号、标题、分类、格式、权限摘要与状态。"
      />

      {/* 筛选栏 */}
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
        <form
          className="relative flex-1 sm:max-w-xs"
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            void load();
          }}
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-secondarytext" aria-hidden />
          <Input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="按标题关键字筛选"
            className="pl-9"
            aria-label="标题关键字"
          />
        </form>
        <Select
          value={status}
          onValueChange={(v) => {
            setStatus(v);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-full sm:w-44" aria-label="状态筛选">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {canDelete && selectedIds.length > 0 && (
          <Button
            variant="destructive"
            onClick={() => setConfirmOpen(true)}
            disabled={overLimit}
            className="shrink-0"
          >
            <Trash2 className="h-4 w-4" aria-hidden />
            批量删除（{selectedIds.length}）
          </Button>
        )}
      </div>

      {overLimit && (
        <p role="alert" className="mb-3 text-[13px] text-danger">
          单次批量删除最多 {BATCH_DELETE_LIMIT} 条，请缩减选择范围。
        </p>
      )}

      {loading && !data ? (
        <PageLoading />
      ) : error && !data ? (
        <ErrorState detail={error} onRetry={() => void load()} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="暂无知识单元"
          description="可前往「知识导入」上传 PDF / Markdown / DOCX / TXT 文档，解析切片后生成知识单元。"
          action={
            <Button onClick={() => navigate("/knowledge/import")} disabled={!can("knowledge:write")}>
              前往知识导入
            </Button>
          }
        />
      ) : (
        <>
          {/* 桌面表格 */}
          <div className="hidden overflow-hidden rounded-lg border border-boundary bg-card md:block">
            <Table>
              <TableHeader>
                <TableRow className="bg-mist/70">
                  {canDelete && (
                    <TableHead className="w-10">
                      <Checkbox
                        checked={allOnPageSelected}
                        onCheckedChange={toggleAll}
                        aria-label="全选本页"
                      />
                    </TableHead>
                  )}
                  <TableHead>编号</TableHead>
                  <TableHead>标题</TableHead>
                  <TableHead>分类</TableHead>
                  <TableHead>格式</TableHead>
                  <TableHead>权限摘要</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead className="text-right">更新时间</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((u) => (
                  <TableRow key={u.id}>
                    {canDelete && (
                      <TableCell>
                        <Checkbox
                          checked={selectedIds.includes(u.id)}
                          onCheckedChange={() => toggleOne(u.id)}
                          aria-label={`选择 ${u.title}`}
                        />
                      </TableCell>
                    )}
                    <TableCell className="code-text text-secondarytext">{u.unit_code}</TableCell>
                    <TableCell className="max-w-[280px] truncate font-medium text-ink" title={u.title}>
                      {u.title}
                    </TableCell>
                    <TableCell className="text-secondarytext">{u.category ?? "—"}</TableCell>
                    <TableCell>
                      <span className="code-text rounded bg-mist px-1.5 py-0.5 text-xs text-secondarytext">
                        {u.file_type?.toUpperCase() ?? "—"}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-[160px] truncate text-[13px] text-secondarytext" title={u.permissions_summary}>
                      {u.permissions_summary}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={u.status} />
                    </TableCell>
                    <TableCell className="text-right text-[13px] text-secondarytext">
                      {formatDateTime(u.updated_at)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* 移动端卡片列表（表格 → 实体卡片） */}
          <div className="space-y-3 md:hidden">
            {data.items.map((u) => (
              <Card key={u.id} className="border-boundary">
                <CardContent className="space-y-2 py-4">
                  <div className="flex items-start justify-between gap-3">
                    <p className="min-w-0 flex-1 font-medium text-ink">{u.title}</p>
                    <StatusBadge status={u.status} />
                  </div>
                  <p className="code-text text-xs text-secondarytext">{u.unit_code} · {u.category ?? "未分类"}</p>
                  <p className="truncate text-[13px] text-secondarytext">{u.permissions_summary}</p>
                  <p className="text-xs text-secondarytext/70">{formatDateTime(u.updated_at)}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* 分页 */}
          <div className="mt-4 flex items-center justify-between">
            <p className="text-[13px] text-secondarytext">
              共 {data.total} 条 · 第 {data.page}/{totalPages} 页
            </p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeft className="h-4 w-4" aria-hidden /> 上一页
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages || loading}
                onClick={() => setPage((p) => p + 1)}
              >
                下一页 <ChevronRight className="h-4 w-4" aria-hidden />
              </Button>
            </div>
          </div>
        </>
      )}

      {/* 批量删除二次确认（破坏性操作） */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-danger">
              <AlertTriangle className="h-5 w-5" aria-hidden /> 确认批量删除
            </DialogTitle>
            <DialogDescription>
              即将删除 <b>{selectedIds.length}</b> 个知识单元及其向量数据，操作不可恢复。
            </DialogDescription>
          </DialogHeader>
          {deleteResult && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger">
              {deleteResult}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={deleting}>
              取消
            </Button>
            <Button variant="destructive" onClick={() => void handleDelete()} disabled={deleting}>
              {deleting ? "删除中…" : "确认删除"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
