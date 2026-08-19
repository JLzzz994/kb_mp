import type { ReactNode } from "react";
import { Hammer } from "lucide-react";
import { EmptyState } from "./PageStates";

/** 模块占位页：列出规划能力 + 建设中状态（后续迭代实现） */
export function ModulePlaceholder({
  title,
  description,
  planned,
  action,
}: {
  title: string;
  description: string;
  planned: string[];
  action?: ReactNode;
}) {
  return (
    <div className="animate-fade-up">
      <h1 className="page-title">{title}</h1>
      <p className="mt-1.5 max-w-2xl text-sm text-secondarytext">{description}</p>

      <div className="mt-6 rounded-lg border border-boundary bg-card p-5">
        <p className="font-display text-sm font-bold text-ink">规划能力（依据 specs）</p>
        <ul className="mt-3 space-y-2">
          {planned.map((p) => (
            <li key={p} className="flex items-start gap-2 text-sm text-primarytext">
              <span aria-hidden className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand" />
              {p}
            </li>
          ))}
        </ul>
      </div>

      <EmptyState
        className="mt-4"
        title="本模块开发中"
        description="当前迭代已交付：登录、数据看板、知识导入、知识单元列表与 AI 鉴权工作台主链路。"
        action={action ?? (
          <span className="flex items-center gap-2 text-sm text-secondarytext">
            <Hammer className="h-4 w-4" aria-hidden /> 下一迭代按 IMPL 计划逐模块交付
          </span>
        )}
      />
    </div>
  );
}
