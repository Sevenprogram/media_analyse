import React from "react";
import {
  ArrowRight,
  BarChart3,
  Building2,
  CheckCircle2,
  KeyRound,
  Loader2,
  Lock,
  Mail,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { api, ApiError } from "../utils/api";
import type { AuthResponse, AuthSession } from "../utils/authSession";
import { toAuthSession } from "../utils/authSession";
import "./auth.css";

export type AuthMode = "login" | "register";

interface AuthPageProps {
  mode: AuthMode;
  onAuthenticated: (session: AuthSession) => void;
  onNavigate: (mode: AuthMode) => void;
}

interface AuthFormState {
  email: string;
  password: string;
  organizationName: string;
  displayName: string;
}

const emptyForm: AuthFormState = {
  email: "",
  password: "",
  organizationName: "",
  displayName: "",
};

export function AuthPage({ mode, onAuthenticated, onNavigate }: AuthPageProps) {
  const isRegister = mode === "register";
  const [form, setForm] = React.useState<AuthFormState>(emptyForm);
  const [error, setError] = React.useState<string | null>(null);
  const [submitting, setSubmitting] = React.useState(false);

  React.useEffect(() => {
    setError(null);
  }, [mode]);

  const updateField = (field: keyof AuthFormState) => (event: React.ChangeEvent<HTMLInputElement>) => {
    setForm((current) => ({ ...current, [field]: event.target.value }));
  };

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (isRegister && form.password.length < 8) {
      setError("密码至少需要 8 位。");
      return;
    }
    if (isRegister && !form.organizationName.trim()) {
      setError("请输入团队或公司名称。");
      return;
    }

    setSubmitting(true);
    try {
      const response = await api<AuthResponse>(isRegister ? "/api/auth/register" : "/api/auth/login", {
        method: "POST",
        body: JSON.stringify(
          isRegister
            ? {
                email: form.email,
                password: form.password,
                organization_name: form.organizationName,
                display_name: form.displayName || null,
              }
            : {
                email: form.email,
                password: form.password,
              },
        ),
      });
      onAuthenticated(toAuthSession(response));
    } catch (requestError) {
      setError(authErrorMessage(requestError, isRegister));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-rail" aria-label="Media Analyse">
        <div className="auth-rail__top">
          <div className="auth-brand">
            <span className="auth-brand__mark">
              <BarChart3 size={21} />
            </span>
            <div>
              <strong>Media Analyse</strong>
              <span>SaaS Console</span>
            </div>
          </div>

          <div className="auth-rail__copy">
            <span>{isRegister ? "New workspace" : "Secure workspace"}</span>
            <h1>{isRegister ? "注册团队工作区" : "登录增长研究工作台"}</h1>
            <p>团队、赛道、采集任务和分析结果会绑定到当前工作区。</p>
          </div>
        </div>

        <div className="auth-status">
          <div className="auth-status__row">
            <ShieldCheck size={17} />
            <span>Tenant boundary</span>
            <strong>Enabled</strong>
          </div>
          <div className="auth-status__row">
            <KeyRound size={17} />
            <span>Bearer auth</span>
            <strong>Active</strong>
          </div>
          <div className="auth-status__row">
            <CheckCircle2 size={17} />
            <span>Research API</span>
            <strong>Protected</strong>
          </div>
        </div>
      </section>

      <section className="auth-panel" aria-label={isRegister ? "注册" : "登录"}>
        <div className="auth-card">
          <div className="auth-mode-switch" role="tablist" aria-label="认证方式">
            <button
              type="button"
              className={mode === "login" ? "is-active" : ""}
              aria-selected={mode === "login"}
              onClick={() => onNavigate("login")}
            >
              登录
            </button>
            <button
              type="button"
              className={mode === "register" ? "is-active" : ""}
              aria-selected={mode === "register"}
              onClick={() => onNavigate("register")}
            >
              注册
            </button>
          </div>

          <header className="auth-card__header">
            <span>{isRegister ? "Create account" : "Welcome back"}</span>
            <h2>{isRegister ? "创建账号" : "登录账号"}</h2>
          </header>

          <form className="auth-form" onSubmit={submit}>
            {isRegister && (
              <label className="auth-field">
                <span>团队名称</span>
                <div className="auth-input">
                  <Building2 size={16} />
                  <input
                    value={form.organizationName}
                    onChange={updateField("organizationName")}
                    placeholder="例如：增长研究团队"
                    autoComplete="organization"
                    required
                  />
                </div>
              </label>
            )}

            {isRegister && (
              <label className="auth-field">
                <span>姓名</span>
                <div className="auth-input">
                  <UserRound size={16} />
                  <input
                    value={form.displayName}
                    onChange={updateField("displayName")}
                    placeholder="用于团队成员识别"
                    autoComplete="name"
                  />
                </div>
              </label>
            )}

            <label className="auth-field">
              <span>邮箱</span>
              <div className="auth-input">
                <Mail size={16} />
                <input
                  type="email"
                  value={form.email}
                  onChange={updateField("email")}
                  placeholder="name@company.com"
                  autoComplete="email"
                  required
                />
              </div>
            </label>

            <label className="auth-field">
              <span>密码</span>
              <div className="auth-input">
                <Lock size={16} />
                <input
                  type="password"
                  value={form.password}
                  onChange={updateField("password")}
                  placeholder={isRegister ? "至少 8 位" : "输入密码"}
                  autoComplete={isRegister ? "new-password" : "current-password"}
                  minLength={isRegister ? 8 : 1}
                  required
                />
              </div>
            </label>

            {error && <div className="auth-error">{error}</div>}

            <button type="submit" className="auth-submit" disabled={submitting}>
              {submitting ? <Loader2 size={17} className="spin" /> : <ArrowRight size={17} />}
              <span>{isRegister ? "创建并进入" : "登录工作台"}</span>
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}

function authErrorMessage(error: unknown, isRegister: boolean) {
  if (error instanceof ApiError) {
    if (error.status === 409) return "该邮箱已注册，请直接登录。";
    if (error.status === 401) return isRegister ? "注册失败，请检查填写内容。" : "邮箱或密码不正确。";
    return error.message;
  }
  return error instanceof Error ? error.message : "请求失败，请稍后重试。";
}
