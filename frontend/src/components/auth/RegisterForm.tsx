import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../../context/AuthContext";
import { useToast } from "../../context/ToastContext";
import { register as registerApi } from "../../api/auth";
import { Input, Button } from "../ui";

const STRENGTH_LABELS: Record<number, { text: string; barClass: string; width: string }> = {
  0: { text: "弱", barClass: "bg-danger", width: "25%" },
  1: { text: "一般", barClass: "bg-danger", width: "50%" },
  2: { text: "中等", barClass: "bg-amber-500", width: "75%" },
  3: { text: "强", barClass: "bg-success", width: "100%" },
  4: { text: "很强", barClass: "bg-success", width: "100%" },
};

const STRENGTH_TEXT_CLASS: Record<number, string> = {
  0: "text-danger",
  1: "text-danger",
  2: "text-amber-500",
  3: "text-success",
  4: "text-success",
};

function passwordStrength(pw: string): number {
  if (!pw) return 0;
  let s = 0;
  if (pw.length >= 12) s++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) s++;
  if (/\d/.test(pw)) s++;
  if (/[^A-Za-z0-9]/.test(pw)) s++;
  return s;
}

interface RegisterFormProps {
  /** Called after successful registration. Default: navigate("/upload"). */
  onSuccess?: () => void;
}

export default function RegisterForm({ onSuccess }: RegisterFormProps) {
  const [mode, setMode] = useState<"email" | "phone">("email");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();

  const strength = passwordStrength(password);
  const s = STRENGTH_LABELS[strength];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (mode === "email" && !email.trim()) {
      setError("请输入邮箱"); return;
    }
    if (mode === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError("请输入正确的邮箱地址"); return;
    }
    if (mode === "phone" && !phone.trim()) {
      setError("请输入手机号"); return;
    }
    if (mode === "phone" && !/^1[3-9]\d{9}$/.test(phone)) {
      setError("请输入正确的11位手机号"); return;
    }
    if (password.length < 8) {
      setError("密码至少需要8个字符，且需包含字母和数字"); return;
    }
    if (strength < 1) {
      setError("密码强度不足，请使用更复杂的密码"); return;
    }

    setLoading(true);
    try {
      const token = await registerApi(
        mode === "email" ? email : "",
        mode === "phone" ? phone : "",
        password
      );
      login(token);
      toast.addToast("success", "注册成功");
      if (onSuccess) {
        onSuccess();
      } else {
        navigate("/upload");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败");
      toast.addToast("error", err instanceof Error ? err.message : "注册失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      {error && (
        <div id="register-error" role="alert" className="rounded-lg bg-danger/10 p-3 text-sm text-danger">
          <p className="mb-1">{error}</p>
          {error.includes("已被注册") && (
            <p className="text-text-secondary">
              已有账号？<Link to="/login" className="text-accent underline">直接登录</Link>
            </p>
          )}
        </div>
      )}

      {/* Email / Phone toggle */}
      <div className="flex gap-2 text-xs">
        <button
          type="button"
          onClick={() => setMode("email")}
          className={`cursor-pointer border-0 bg-transparent ${mode === "email" ? "font-semibold text-accent" : "font-normal text-text-secondary"}`}
        >
          邮箱注册
        </button>
        <span className="text-text-secondary">|</span>
        <button
          type="button"
          onClick={() => setMode("phone")}
          className={`cursor-pointer border-0 bg-transparent ${mode === "phone" ? "font-semibold text-accent" : "font-normal text-text-secondary"}`}
        >
          手机号注册
        </button>
      </div>

      {mode === "email" ? (
        <Input type="email" placeholder="邮箱" value={email}
          onChange={(e) => setEmail(e.target.value)} aria-label="邮箱"
          aria-invalid={!!error} aria-describedby={error ? "register-error" : undefined}
          required />
      ) : (
        <Input type="tel" placeholder="11位手机号" value={phone}
          onChange={(e) => setPhone(e.target.value)} aria-label="手机号"
          aria-invalid={!!error} aria-describedby={error ? "register-error" : undefined}
          required maxLength={11} />
      )}

      <div className="relative">
        <Input type={showPw ? "text" : "password"} placeholder="密码（至少8位）" value={password}
          onChange={(e) => setPassword(e.target.value)} aria-label="密码"
          aria-invalid={!!error} aria-describedby={error ? "register-error" : undefined}
          required minLength={8} className="pr-10" />
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

      {password && (
        <div className="mt-2">
          <div className="h-1 overflow-hidden rounded bg-border">
            <div className={`h-full rounded transition-[width] duration-300 ${s.barClass}`} style={{ width: s.width }} />
          </div>
          <div className={`mt-1 text-xs ${STRENGTH_TEXT_CLASS[strength]}`}>
            密码强度：{s.text}
          </div>
        </div>
      )}

      <Button type="submit" disabled={loading}>
        {loading ? "注册中..." : "注册"}
      </Button>
    </form>
  );
}
