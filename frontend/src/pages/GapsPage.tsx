import { ModulePlaceholder } from "@/components/shared/ModulePlaceholder";

export default function GapsPage() {
  return (
    <ModulePlaceholder
      title="知识缺口"
      description="聚类未命中问题模式，一键建档补齐知识（gap:read，建档需 knowledge:write）。"
      planned={[
        "缺口列表：问题模式、样例问题（≤20 条）、ask_count、last_asked_at、状态筛选",
        "一键建档：预填 question_pattern 与样例，确认正文 + 四维权限后创建知识单元",
        "状态流转：unresolved → resolved（回填 resolved_unit_id）/ ignored",
      ]}
    />
  );
}
