import type { ReactNode } from "react";
import { Loader2, Inbox } from "lucide-react";
import { cn } from "@/lib/utils";

export function PageLoading() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center" role="status" aria-label="加载中">
      <Loader2 className="h-6 w-6 animate-spin text-brand" aria-hidden />
      <span className="ml-3 text-secondarytext">加载中…</span>
    </div>
  );
}

/** 空状态：解释原因 + 唯一主要操作（原型设计说明 §5） */
export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-dashed border-boundary bg-card/60 px-6 py-14 text-center",
        className,
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-mist">
        <Inbox className="h-6 w-6 text-secondarytext" aria-hidden />
      </div>
      <p className="mt-4 font-display text-base font-bold text-ink">{title}</p>
      {description && <p className="mt-1.5 max-w-sm text-sm text-secondarytext">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** 失败状态：红色提示并提供下一步操作 */
export function ErrorState({
  detail,
  onRetry,
  className,
}: {
  detail: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-danger/30 bg-danger-soft px-6 py-12 text-center",
        className,
      )}
    >
      <p className="font-display text-base font-bold text-danger">加载失败</p>
      <p className="mt-1.5 max-w-md text-sm text-primarytext/80">{detail}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-5 min-h-[44px] rounded-md bg-danger px-5 font-medium text-white transition hover:opacity-90"
        >
          重试
        </button>
      )}
    </div>
  );
}
