import { useState, useEffect } from "react";
import { useNavigate, Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { useToast } from "../../context/ToastContext";
import { login as loginApi } from "../../api/auth";
import { Input, Button } from "../ui";

type LoginMode = "email" | "phone";

interface LoginFormProps {
  /** Called after successful login. Default: navigate("/upload"). */
  onSuccess?: () => void;
}

export default function LoginForm({ onSuccess }: LoginFormProps) {
  const [mode, setMode] = useState<LoginMode>("email");
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [searchParams] = useSearchParams();

  useEffect(() => {
    if (searchParams.get("expired") === "1") {
      setError("登录已过期，请重新登录");
    }
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    const v = account.trim();
    if (!v) {
      setError(mode === "email" ? "请输入邮箱" : "请输入手机号");
      return;
    }
    if (mode === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) {
      setError("请输入正确的邮箱地址");
      return;
    }
    if (mode === "phone" && !/^1[3-9]\d{9}$/.test(v)) {
      setError("请输入正确的 11 位手机号");
      return;
    }
    if (!password) {
      setError("请输入密码");
      return;
    }

    setLoading(true);
    try {
      const token = await loginApi(v, password);
      login(token);
      toast.addToast("success", "登录成功");
      // Honor ?redirect= if present and points to an internal path.
      const params = new URLSearchParams(searchParams);
      const redirect = params.get("redirect");
      const safeRedirect =
        redirect && redirect.startsWith("/") && !redirect.startsWith("//")
          ? decodeURIComponent(redirect)
          : null;
      if (safeRedirect) {
        navigate(safeRedirect);
      } else if (onSuccess) {
        onSuccess();
      } else {
        navigate("/upload");
      }
    } catch (err) {
      // D1.4: do not surface backend wording that distinguishes "wrong
      // password" from "no such account" — both leak account existence.
      const raw = err instanceof Error ? err.message : "登录失败";
      const msg = /账号|密码|用户|不存在|未注册/i.test(raw)
        ? "账号或密码错误"
        : raw;
      setError(msg);
      toast.addToast("error", msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {error && (
        <div id="login-error" role="alert" className="rounded-lg bg-danger/10 p-3 text-sm text-danger">
          <p className="mb-1">{error}</p>
          <p className="text-text-secondary">
            还没有账号？<Link to="/register" className="text-accent underline">立即注册</Link>
          </p>
        </div>
      )}

      {/* D1.2: email / phone mode toggle (mirrors the register form) */}
      <div className="flex gap-2 text-xs">
        <button
          type="button"
          onClick={() => setMode("email")}
          className={`cursor-pointer border-0 bg-transparent ${mode === "email" ? "font-semibold text-accent" : "font-normal text-text-secondary"}`}
        >
          邮箱登录
        </button>
        <span className="text-text-secondary">|</span>
        <button
          type="button"
          onClick={() => setMode("phone")}
          className={`cursor-pointer border-0 bg-transparent ${mode === "phone" ? "font-semibold text-accent" : "font-normal text-text-secondary"}`}
        >
          手机号登录
        </button>
      </div>

      <Input
        type={mode === "email" ? "email" : "tel"}
        placeholder={mode === "email" ? "邮箱" : "11位手机号"}
        value={account}
        onChange={(e) => setAccount(e.target.value)}
        aria-label={mode === "email" ? "邮箱" : "手机号"}
        aria-invalid={!!error}
        aria-describedby={error ? "login-error" : undefined}
        required
        maxLength={mode === "phone" ? 11 : undefined}
      />
      <div className="relative">
        <Input
          type={showPw ? "text" : "password"}
          placeholder="密码（至少8位）"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-label="密码"
          required
          minLength={8}
          className="pr-10"
        />
        <button
          type="button"
          onClick={() => setShowPw(!showPw)}
          aria-label={showPw ? "隐藏密码" : "显示密码"}
          className="absolute right-3 top-1/2 -translate-y-1/2 cursor-pointer border-0 bg-transparent p-1 text-text-secondary hover:text-text-primary focus-ring"
        >
          {showPw ? (
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
              <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
              <line x1="1" y1="1" x2="23" y2="23" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          )}
        </button>
      </div>
      <Button type="submit" disabled={loading}>
        {loading ? "登录中..." : "登录"}
      </Button>
    </form>
  );
}
