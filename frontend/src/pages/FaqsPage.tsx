import { ModulePlaceholder } from "@/components/shared/ModulePlaceholder";

export default function FaqsPage() {
  return (
    <ModulePlaceholder
      title="FAQ 管理"
      description="自动挖掘推荐 + 人工录入 + 审核发布与缓存（faq:read / faq:write / faq:review）。"
      planned={[
        "推荐列表：status=pending_review，展示频次、关联知识单元、建议答案",
        "审核弹窗：action（approve / reject）+ edited_answer（仅 approve 可编辑标准答案）",
        "已发布 FAQ：缓存状态与 hit_count 命中次数；下线（DELETE）二次确认",
        "发布时快照 unit_updated_at，关联知识更新后缓存自动失效",
      ]}
    />
  );
}
