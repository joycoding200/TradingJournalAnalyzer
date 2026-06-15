import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { login as loginApi } from "../api/auth";

export default function Login() {
  const [account, setAccount] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const token = await loginApi(account, password);
      login(token);
      navigate("/upload");
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-[80vh] px-4">
      <div
        style={{
          backgroundColor: "var(--bg-secondary)",
          borderRadius: "12px",
          border: "1px solid var(--border)",
        }}
        className="w-full max-w-sm p-8"
      >
        <h1 className="text-xl font-semibold mb-6 text-center">登录</h1>
        {error && (
          <div
            className="text-sm mb-4 p-3 rounded-lg"
            style={{ backgroundColor: "rgba(248,113,113,0.1)", color: "var(--danger)" }}
          >
            {error}
          </div>
        )}
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <input
            type="email"
            placeholder="邮箱或手机号"
            value={account}
            onChange={(e) => setAccount(e.target.value)}
            required
            style={{
              backgroundColor: "var(--bg-tertiary)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              color: "var(--text-primary)",
            }}
            className="px-4 py-3 text-sm outline-none focus:border-[var(--accent)]"
          />
          <div style={{ position: "relative" }}>
            <input
              type={showPw ? "text" : "password"}
              placeholder="密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border)", borderRadius: "8px", color: "var(--text-primary)" }}
              className="px-4 py-3 pr-10 text-sm outline-none focus:border-[var(--accent)] w-full"
            />
            <button type="button" onClick={() => setShowPw(!showPw)}
              style={{ position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "var(--text-secondary)", fontSize: 16, padding: 4, lineHeight: 1 }}>
              {showPw ? "🙈" : "👁"}
            </button>
          </div>
          <button
            type="submit"
            disabled={loading}
            style={{
              backgroundColor: "var(--accent)",
              color: "#fff",
              border: "none",
              borderRadius: "8px",
              padding: "12px",
              cursor: "pointer",
              opacity: loading ? 0.6 : 1,
            }}
            className="text-sm font-medium"
          >
            {loading ? "登录中..." : "登录"}
          </button>
        </form>
        <p className="text-sm mt-4 text-center" style={{ color: "var(--text-secondary)" }}>
          没有账号？{" "}
          <Link to="/register" style={{ color: "var(--accent)" }}>
            注册
          </Link>
        </p>
      </div>
    </div>
  );
}
