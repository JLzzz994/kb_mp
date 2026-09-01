import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useState } from "react";
import { Loader2, ShieldCheck, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { login } from "@/api/auth";
import { ApiError } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";

const loginSchema = z.object({
  username: z
    .string()
    .min(3, "用户名至少 3 个字符")
    .max(64, "用户名最多 64 个字符")
    .regex(/^[a-zA-Z0-9_]+$/, "仅支持字母、数字与下划线"),
  password: z.string().min(6, "密码至少 6 位").max(128, "密码最多 128 位"),
});

type LoginForm = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setSession } = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: "", password: "" },
  });

  const onSubmit = async (values: LoginForm) => {
    setServerError(null);
    try {
      const resp = await login(values.username, values.password);
      setSession(resp.user_info, resp.permissions);
      const redirect = searchParams.get("redirect");
      navigate(redirect && redirect.startsWith("/") ? redirect : "/", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setServerError(
          err.status === 401 ? "用户名或密码错误，或账号已被停用" : `登录失败：${err.message}`,
        );
      } else {
        setServerError("网络异常，请稍后重试");
      }
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-2xl border border-boundary bg-card shadow-xl shadow-ink/5 md:grid-cols-[1.05fr_1fr]">
        <section className="relative hidden flex-col justify-between bg-navy p-10 text-white md:flex">
          <div>
            <p className="code-text text-brand">HUICE · ERP/WMS</p>
            <h1 className="mt-4 font-display text-[32px] font-extrabold leading-tight tracking-tight">
              产品知识运营平台
              <br />
              权限可控的 RAG 问答
            </h1>
            <p className="mt-4 max-w-xs text-sm leading-relaxed text-white/60">
              产品文档 · 实施规范 · 客服 FAQ · 权限过滤 · 知识缺口 · 引用追溯
            </p>
          </div>
          <div className="mt-10">
            <div className="permission-pulse-line" aria-hidden />
            <div className="mt-4 flex items-center gap-2 text-xs text-white/50">
              <ShieldCheck className="h-4 w-4 text-brand" aria-hidden />
              面向产品、实施、客服和客户成功团队，召回后先鉴权再回答
            </div>
          </div>
        </section>

        <section className="p-8 sm:p-10">
          <h2 className="font-display text-2xl font-extrabold tracking-tight text-ink">登录</h2>
          <p className="mt-1.5 text-sm text-secondarytext">进入 ERP/WMS 产品知识运营管理台</p>

          {serverError && (
            <div
              role="alert"
              className="mt-5 flex items-start gap-2.5 rounded-md border border-danger/40 bg-danger-soft px-4 py-3 text-sm text-danger"
            >
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
              {serverError}
            </div>
          )}

          <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-5" noValidate>
            <div className="space-y-2">
              <Label htmlFor="username">用户名</Label>
              <Input
                id="username"
                autoComplete="username"
                placeholder="admin"
                aria-invalid={Boolean(errors.username)}
                aria-describedby={errors.username ? "username-error" : undefined}
                {...register("username")}
              />
              {errors.username && (
                <p id="username-error" role="alert" className="text-[13px] text-danger">
                  {errors.username.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="password">密码</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                placeholder="••••••••"
                aria-invalid={Boolean(errors.password)}
                aria-describedby={errors.password ? "password-error" : undefined}
                {...register("password")}
              />
              {errors.password && (
                <p id="password-error" role="alert" className="text-[13px] text-danger">
                  {errors.password.message}
                </p>
              )}
            </div>

            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> 登录中…
                </>
              ) : (
                "登 录"
              )}
            </Button>
          </form>

          <p className="mt-6 text-xs leading-relaxed text-secondarytext">
            演示账号：admin（平台管理员）/ kadmin（产品知识管理员）/ alice（实施顾问），密码见 seed 数据。
          </p>
        </section>
      </div>
    </div>
  );
}
