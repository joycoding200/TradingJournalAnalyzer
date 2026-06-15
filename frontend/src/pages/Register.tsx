import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { register as registerApi } from "../api/auth";

const STRENGTH_LABELS: Record<number, { text: string; color: string; width: string }> = {
  0: { text: "弱", color: "var(--danger)", width: "25%" },
  1: { text: "一般", color: "var(--danger)", width: "50%" },
  2: { text: "中等", color: "#f59e0b", width: "75%" },
  3: { text: "强", color: "var(--success)", width: "100%" },
  4: { text: "很强", color: "var(--success)", width: "100%" },
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

export default function Register() {
  const [mode, setMode] = useState<"email" | "phone">("email");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const strength = passwordStrength(password);
  const s = STRENGTH_LABELS[strength];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (mode === "email" && !email.includes("@")) {
      setError("请输入正确的邮箱地址"); return;
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
      navigate("/upload");
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-[80vh] px-4">
      <div
        style={{ backgroundColor: "var(--bg-secondary)", borderRadius: "12px", border: "1px solid var(--border)" }}
        className="w-full max-w-sm p-8"
      >
        <h1 className="text-xl font-semibold mb-6 text-center">注册</h1>
        {error && (
          <div className="text-sm mb-4 p-3 rounded-lg" style={{ backgroundColor: "rgba(248,113,113,0.1)", color: "var(--danger)" }}>
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {/* Email / Phone toggle */}
          <div className="flex gap-2 text-xs" style={{ color: "var(--text-secondary)" }}>
            <button type="button" onClick={() => setMode("email")}
              style={{ border: "none", background: "none", cursor: "pointer",
                color: mode === "email" ? "var(--accent)" : "var(--text-secondary)", fontWeight: mode === "email" ? 600 : 400 }}>
              邮箱注册
            </button>
            <span>|</span>
            <button type="button" onClick={() => setMode("phone")}
              style={{ border: "none", background: "none", cursor: "pointer",
                color: mode === "phone" ? "var(--accent)" : "var(--text-secondary)", fontWeight: mode === "phone" ? 600 : 400 }}>
              手机号注册
            </button>
          </div>

          {mode === "email" ? (
            <input type="email" placeholder="请输入邮箱" value={email}
              onChange={(e) => setEmail(e.target.value)} required
              style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text-primary)" }}
              className="px-4 py-3 text-sm outline-none focus:border-[var(--accent)]" />
          ) : (
            <input type="tel" placeholder="请输入11位手机号" value={phone}
              onChange={(e) => setPhone(e.target.value)} required maxLength={11}
              style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text-primary)" }}
              className="px-4 py-3 text-sm outline-none focus:border-[var(--accent)]" />
          )}

          <div style={{ position: "relative" }}>
            <input type={showPw ? "text" : "password"} placeholder="密码（至少8位，含字母+数字）" value={password}
              onChange={(e) => setPassword(e.target.value)} required minLength={8}
              style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text-primary)" }}
              className="px-4 py-3 pr-10 text-sm outline-none focus:border-[var(--accent)] w-full" />
            <button type="button" onClick={() => setShowPw(!showPw)}
              style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)", fontSize: 16, padding: 4, lineHeight: 1 }}>
              {showPw ? "🙈" : "👁"}
            </button>
            {password && (
              <div className="mt-2">
                <div style={{ backgroundColor: "var(--border)", borderRadius: 4, height: 4, overflow: "hidden" }}>
                  <div style={{ width: s.width, height: "100%", backgroundColor: s.color, borderRadius: 4, transition: "width 0.3s" }} />
                </div>
                <div className="text-xs mt-1" style={{ color: s.color }}>密码强度：{s.text}</div>
              </div>
            )}
          </div>

          <button type="submit" disabled={loading}
            style={{ backgroundColor: "var(--accent)", color: "#fff", border: "none", borderRadius: "8px", padding: "12px", cursor: "pointer", opacity: loading ? 0.6 : 1 }}
            className="text-sm font-medium">
            {loading ? "注册中..." : "注册"}
          </button>
        </form>
        <p className="text-sm mt-4 text-center" style={{ color: "var(--text-secondary)" }}>
          已有账号？<Link to="/login" style={{ color: "var(--accent)" }}>登录</Link>
        </p>
      </div>
    </div>
  );
}
