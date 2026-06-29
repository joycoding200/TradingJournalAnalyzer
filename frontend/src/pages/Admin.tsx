import { useState } from "react";
import { apiFetch } from "../api/client";
import { Card, Input, Button, LoadingSpinner } from "../components/ui";

interface UserItem {
  id: string; email: string; phone: string; nickname: string; created_at: string;
  file_count: number; analysis_count: number; report_count: number;
}
interface FileItem { id: string; filename: string; source_type: string; uploaded_at: string; }
interface AnalysisItem { id: string; filename: string; date_start: string; date_end: string; created_at: string; has_snapshot: boolean; has_report: boolean; }

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
  const [lastLogin, setLastLogin] = useState<{ at: string; ip: string } | null>(null);

  const adminHeaders = (extra?: Record<string, string>) => ({
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    ...extra,
  });

  const adminGet = async (path: string): Promise<any> => {
    const resp = await apiFetch(path, { headers: adminHeaders() });
    if (!resp.ok) {
      const e = await resp.json().catch(() => ({ detail: "请求失败" }));
      throw new Error(e.detail);
    }
    return resp.json();
  };

  const adminDownload = async (path: string, filename: string) => {
    const resp = await apiFetch(path, { headers: adminHeaders() });
    if (!resp.ok) throw new Error("下载失败");
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleLogin = async () => {
    setError("");
    try {
      const resp = await apiFetch("/api/admin/login", {
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
      // D3.3: capture previous login info returned by the backend
      if (data.last_login_at) {
        setLastLogin({ at: data.last_login_at, ip: data.last_login_ip || "" });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "登录失败");
    }
  };

  const handleSearch = async () => {
    setLoading(true);
    try {
      const data = await adminGet(`/api/admin/users?q=${encodeURIComponent(search)}`);
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
        adminGet(`/api/admin/users/${u.id}/files`),
        adminGet(`/api/admin/users/${u.id}/analyses`),
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
        <Card className="w-full max-w-sm p-8">
          <h1 className="text-xl font-semibold mb-6 text-center">管理员登录</h1>
          {error && <div className="text-sm mb-4 p-3 rounded-lg bg-danger/10 text-danger">{error}</div>}
          <div className="flex flex-col gap-4">
            <Input value={user} onChange={e => setUser(e.target.value)} placeholder="管理员账号" />
            <Input type="password" value={pass} onChange={e => setPass(e.target.value)} placeholder="密码"
              onKeyDown={e => e.key === "Enter" && handleLogin()} />
            <Button onClick={handleLogin}>登录</Button>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-6">
        <h1 className="text-xl font-semibold">管理员面板</h1>
        <div className="flex items-center gap-3">
          {lastLogin?.at && (
            <span className="text-xs text-text-secondary">
              上次登录：{lastLogin.at}{lastLogin.ip ? ` · ${lastLogin.ip}` : ""}
            </span>
          )}
          <button onClick={() => { setToken(""); localStorage.removeItem("admin_token"); setLastLogin(null); }}
            className="text-xs text-text-secondary bg-transparent border-0 cursor-pointer">
            退出
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="flex gap-2 mb-6">
        <div className="flex-1">
          <Input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索用户（邮箱/昵称）"
            onKeyDown={e => e.key === "Enter" && handleSearch()} />
        </div>
        <Button onClick={handleSearch} disabled={loading}>
          {loading ? "..." : "搜索"}
        </Button>
      </div>

      {/* User list */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-6">
        {users.map(u => (
          <div key={u.id} onClick={() => selectUser(u)}
            className={`p-4 rounded-xl cursor-pointer transition-[background-color,border-color] duration-150 ${
              selected?.id === u.id
                ? "bg-accent/10 border border-accent"
                : "bg-bg-secondary border border-border"
            }`}>
            <div className="font-medium">{u.nickname || u.email || u.phone}</div>
            <div className="text-xs mt-1 text-text-secondary">
              {u.email}{u.phone ? ` · ${u.phone}` : ""}
            </div>
            <div className="text-xs mt-1 text-text-secondary">
              📄{u.file_count} 份交割单 · 📊{u.analysis_count} 次分析 · 📝{u.report_count} 份报告
            </div>
          </div>
        ))}
      </div>

      {/* Selected user details */}
      {selected && loading && <LoadingSpinner text="加载数据..." />}
      {selected && !loading && (
        <div>
          <h2 className="text-sm font-medium mb-4 text-text-secondary">
            {selected.nickname || selected.email} 的数据
          </h2>

          <h3 className="text-xs font-medium mb-2 text-text-secondary">上传的交割单</h3>
          <div className="flex flex-col gap-2 mb-4">
            {files.map(f => (
              <Card key={f.id} className="flex items-center justify-between p-3">
                <div>
                  <span className="text-sm">📄 {f.filename}</span>
                  <span className="text-xs ml-2 text-text-secondary">{f.source_type} · {f.uploaded_at?.slice(0, 10)}</span>
                </div>
                <button
                  onClick={() => adminDownload(`/api/admin/download/raw/${f.id}`, f.filename)}
                  className="border-0 cursor-pointer bg-transparent text-xs text-accent"
                >
                  ⬇ 下载
                </button>
              </Card>
            ))}
            {files.length === 0 && <div className="text-xs text-text-secondary">无文件</div>}
          </div>

          <h3 className="text-xs font-medium mb-2 text-text-secondary">分析记录</h3>
          <div className="flex flex-col gap-2">
            {analyses.map(a => (
              <Card key={a.id} className="flex items-center justify-between p-3">
                <div>
                  <span className="text-sm">{a.filename ? `📄 ${a.filename}` : `分析 ${a.id.slice(0, 8)}`}</span>
                  <span className="text-xs ml-2 text-text-secondary">{a.date_start}~{a.date_end}</span>
                </div>
                <div className="flex gap-3">
                  <button
                    onClick={() => adminDownload(`/api/admin/download/analysis/${a.id}`, `analysis_${a.id.slice(0,8)}.json`)}
                    className="border-0 cursor-pointer bg-transparent text-xs text-accent"
                  >
                    📊 下载
                  </button>
                  {a.has_report && (
                    <button
                      onClick={() => adminDownload(`/api/admin/download/report/${a.id}`, `report_${a.id.slice(0,8)}.md`)}
                      className="border-0 cursor-pointer bg-transparent text-xs text-accent"
                    >
                      📝 下载
                    </button>
                  )}
                </div>
              </Card>
            ))}
            {analyses.length === 0 && <div className="text-xs text-text-secondary">无分析记录</div>}
          </div>
        </div>
      )}
    </div>
  );
}
