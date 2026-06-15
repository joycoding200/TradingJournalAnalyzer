import { useState } from "react";

interface UserItem {
  id: string; email: string; phone: string; nickname: string; created_at: string;
  file_count: number; analysis_count: number; report_count: number;
}
interface FileItem { id: string; filename: string; source_type: string; uploaded_at: string; }
interface AnalysisItem { id: string; filename: string; date_start: string; date_end: string; created_at: string; has_snapshot: boolean; has_report: boolean; }

const BASE = "http://localhost:8000";

export default function Admin() {
  const [token, setToken] = useState(localStorage.getItem("admin_token") || "");
  const [user, setUser] = useState("");
  const [pass, setPass] = useState("");
  const [error, setError] = useState("");
  const [users, setUsers] = useState<UserItem[]>([]);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<UserItem | null>(null);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [analyses, setAnalyses] = useState<AnalysisItem[]>([]);
  const [loading, setLoading] = useState(false);

  const headers = (extra?: Record<string, string>) => ({
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    ...extra,
  });

  const adminFetch = async (path: string): Promise<any> => {
    const resp = await fetch(`${BASE}${path}`, { headers: headers() });
    if (!resp.ok) {
      const e = await resp.json().catch(() => ({ detail: "请求失败" }));
      throw new Error(e.detail);
    }
    return resp.json();
  };

  const handleLogin = async () => {
    setError("");
    try {
      const resp = await fetch(`${BASE}/api/admin/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: user, password: pass }),
      });
      if (!resp.ok) {
        const e = await resp.json().catch(() => ({ detail: "登录失败" }));
        throw new Error(e.detail);
      }
      const data = await resp.json();
      setToken(data.access_token);
      localStorage.setItem("admin_token", data.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    }
  };

  const handleSearch = async () => {
    setLoading(true);
    try {
      const data = await adminFetch(`/api/admin/users?q=${encodeURIComponent(search)}`);
      setUsers(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "搜索失败");
    } finally { setLoading(false); }
  };

  const selectUser = async (u: UserItem) => {
    setSelected(u);
    setLoading(true);
    try {
      const [f, a] = await Promise.all([
        adminFetch(`/api/admin/users/${u.id}/files`),
        adminFetch(`/api/admin/users/${u.id}/analyses`),
      ]);
      setFiles(f); setAnalyses(a);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally { setLoading(false); }
  };

  // Login screen
  if (!token) {
    return (
      <div className="flex items-center justify-center min-h-[80vh] px-4">
        <div style={{ backgroundColor: "var(--bg-secondary)", borderRadius: 12, border: "1px solid var(--border)" }} className="w-full max-w-sm p-8">
          <h1 className="text-xl font-semibold mb-6 text-center">管理员登录</h1>
          {error && <div className="text-sm mb-4 p-3 rounded-lg" style={{ backgroundColor: "rgba(248,113,113,0.1)", color: "var(--danger)" }}>{error}</div>}
          <div className="flex flex-col gap-4">
            <input value={user} onChange={e => setUser(e.target.value)} placeholder="管理员账号"
              style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-primary)" }}
              className="px-4 py-3 text-sm outline-none" />
            <input type="password" value={pass} onChange={e => setPass(e.target.value)} placeholder="密码"
              onKeyDown={e => e.key === "Enter" && handleLogin()}
              style={{ backgroundColor: "var(--bg-tertiary)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-primary)" }}
              className="px-4 py-3 text-sm outline-none" />
            <button onClick={handleLogin}
              style={{ backgroundColor: "var(--accent)", color: "#fff", border: "none", borderRadius: 8, padding: 12, cursor: "pointer" }}
              className="text-sm font-medium">登录</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">管理员面板</h1>
        <button onClick={() => { setToken(""); localStorage.removeItem("admin_token"); }}
          className="text-xs" style={{ color: "var(--text-secondary)", background: "none", border: "none", cursor: "pointer" }}>
          退出
        </button>
      </div>

      {/* Search */}
      <div className="flex gap-2 mb-6">
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索用户（邮箱/昵称）"
          onKeyDown={e => e.key === "Enter" && handleSearch()}
          style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)", borderRadius: 8, color: "var(--text-primary)", flex: 1 }}
          className="px-4 py-2 text-sm outline-none" />
        <button onClick={handleSearch} disabled={loading}
          style={{ backgroundColor: "var(--accent)", color: "#fff", border: "none", borderRadius: 8, padding: "8px 20px", cursor: "pointer" }}
          className="text-sm">{loading ? "..." : "搜索"}</button>
      </div>

      {/* User list */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
        {users.map(u => (
          <div key={u.id} onClick={() => selectUser(u)}
            style={{ backgroundColor: selected?.id === u.id ? "rgba(59,130,246,0.1)" : "var(--bg-secondary)", border: `1px solid ${selected?.id === u.id ? "var(--accent)" : "var(--border)"}`, borderRadius: 12, cursor: "pointer" }}
            className="p-4">
            <div className="font-medium">{u.nickname || u.email || u.phone}</div>
            <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
              {u.email}{u.phone ? ` · ${u.phone}` : ""}
            </div>
            <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
              📄{u.file_count} 份交割单 · 📊{u.analysis_count} 次分析 · 📝{u.report_count} 份报告
            </div>
          </div>
        ))}
      </div>

      {/* Selected user details */}
      {selected && (
        <div>
          <h2 className="text-sm font-medium mb-4" style={{ color: "var(--text-secondary)" }}>
            {selected.nickname || selected.email} 的数据
          </h2>

          <h3 className="text-xs font-medium mb-2" style={{ color: "var(--text-secondary)" }}>上传的交割单</h3>
          <div className="flex flex-col gap-2 mb-4">
            {files.map(f => (
              <div key={f.id} className="flex items-center justify-between p-3 rounded-lg"
                style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
                <div>
                  <span className="text-sm">📄 {f.filename}</span>
                  <span className="text-xs ml-2" style={{ color: "var(--text-secondary)" }}>{f.source_type} · {f.uploaded_at?.slice(0, 10)}</span>
                </div>
                <a href={`${BASE}/api/admin/download/raw/${f.id}`} target="_blank" rel="noreferrer"
                  onClick={e => { e.preventDefault();
                    const a = document.createElement("a"); a.href = `${BASE}/api/admin/download/raw/${f.id}`;
                    const h = headers(); a.setAttribute("download", f.filename);
                    fetch(`${BASE}/api/admin/download/raw/${f.id}`, { headers: h() })
                      .then(r => r.blob()).then(b => { a.href = URL.createObjectURL(b); a.click(); }); }}
                  style={{ color: "var(--accent)", textDecoration: "none", fontSize: 13, cursor: "pointer" }}>
                  ⬇ 下载
                </a>
              </div>
            ))}
            {files.length === 0 && <div className="text-xs" style={{ color: "var(--text-secondary)" }}>无文件</div>}
          </div>

          <h3 className="text-xs font-medium mb-2" style={{ color: "var(--text-secondary)" }}>分析记录</h3>
          <div className="flex flex-col gap-2">
            {analyses.map(a => (
              <div key={a.id} className="flex items-center justify-between p-3 rounded-lg"
                style={{ backgroundColor: "var(--bg-secondary)", border: "1px solid var(--border)" }}>
                <div>
                  <span className="text-sm">{a.filename ? `📄 ${a.filename}` : `分析 ${a.id.slice(0, 8)}`}</span>
                  <span className="text-xs ml-2" style={{ color: "var(--text-secondary)" }}>{a.date_start}~{a.date_end}</span>
                </div>
                <div className="flex gap-3">
                  <a href={`${BASE}/api/admin/download/analysis/${a.id}`} target="_blank" rel="noreferrer"
                    onClick={e => { e.preventDefault(); fetch(`${BASE}/api/admin/download/analysis/${a.id}`, { headers: headers() })
                      .then(r => r.blob()).then(b => { const url = URL.createObjectURL(b); const a2 = document.createElement("a"); a2.href = url; a2.download = `analysis_${a.id.slice(0,8)}.json`; a2.click(); }); }}
                    style={{ color: "var(--accent)", fontSize: 13, textDecoration: "none", cursor: "pointer" }}>
                    📊 下载
                  </a>
                  {a.has_report && (
                    <a href={`${BASE}/api/admin/download/report/${a.id}`} target="_blank" rel="noreferrer"
                      onClick={e => { e.preventDefault(); fetch(`${BASE}/api/admin/download/report/${a.id}`, { headers: headers() })
                        .then(r => r.blob()).then(b => { const url = URL.createObjectURL(b); const a2 = document.createElement("a"); a2.href = url; a2.download = `report_${a.id.slice(0,8)}.md`; a2.click(); }); }}
                      style={{ color: "var(--accent)", fontSize: 13, textDecoration: "none", cursor: "pointer" }}>
                      📝 下载
                    </a>
                  )}
                </div>
              </div>
            ))}
            {analyses.length === 0 && <div className="text-xs" style={{ color: "var(--text-secondary)" }}>无分析记录</div>}
          </div>
        </div>
      )}
    </div>
  );
}
