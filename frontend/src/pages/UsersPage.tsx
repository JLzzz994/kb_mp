import { ModulePlaceholder } from "@/components/shared/ModulePlaceholder";

export default function UsersPage() {
  return (
    <ModulePlaceholder
      title="用户管理"
      description="维护系统登录主体：账号、归属部门、角色分配与启停用。"
      planned={[
        "用户列表：分页 + 关键字 / 部门 / 状态筛选（user:read）",
        "新建用户：username（3–64，字母数字下划线）/ password（8–128）/ display_name / 单部门归属 / role_ids ≥ 1",
        "启停用（PATCH status）与重置密码（new_password 8–128），均需 user:write",
        "破坏性操作二次确认；错误时保留表单输入",
      ]}
    />
  );
}
