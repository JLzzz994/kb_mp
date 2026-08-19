import { ModulePlaceholder } from "@/components/shared/ModulePlaceholder";

export default function ProfilePage() {
  return (
    <ModulePlaceholder
      title="个人中心"
      description="当前登录主体信息与密码修改。"
      planned={[
        "展示 CurrentUserInfo：username、display_name、department_name、role_codes、权限码列表",
        "修改密码：new_password（8–128），当前密码校验",
        "退出登录：清 token 回登录页",
      ]}
    />
  );
}
