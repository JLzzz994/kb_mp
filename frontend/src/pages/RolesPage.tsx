import { ModulePlaceholder } from "@/components/shared/ModulePlaceholder";

export default function RolesPage() {
  return (
    <ModulePlaceholder
      title="角色与操作权限"
      description="三种内置角色 + 17 权限码分配（role:read / role:write）。"
      planned={[
        "角色列表：system_admin（17 码）/ knowledge_admin（14 码）/ regular_user（4 码）",
        "权限分配：permission_codes 多选 + permission_type（menu / button / api）",
        "内置角色不可删除；权限变更后 Redis 位图缓存失效（5 分钟 TTL）",
      ]}
    />
  );
}
