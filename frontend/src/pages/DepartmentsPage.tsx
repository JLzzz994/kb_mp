import { ModulePlaceholder } from "@/components/shared/ModulePlaceholder";

export default function DepartmentsPage() {
  return (
    <ModulePlaceholder
      title="部门管理"
      description="树形组织节点（parent_id 自引用），用户单一归属部门。"
      planned={[
        "部门树：嵌套 children 结构，sort_order + id 稳定排序",
        "新建 / 编辑：name（1–64）、parent_id、leader_id、sort_order",
        "删除保护：部门下存在用户时返回 department_not_empty",
        "部门权限向上继承：用户当前部门 + 祖先部门参与知识四维鉴权",
      ]}
    />
  );
}
