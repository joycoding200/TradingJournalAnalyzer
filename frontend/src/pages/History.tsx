import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listReports } from "../api/report";

interface ReportItem {
  id: string;
  analysis_id?: string;
  filename?: string;
  created_at?: string;
  title?: string;
}

export default function History() {
  const [reports, setReports] = useState<ReportItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    listReports()
      .then((data) => {
        setReports(Array.isArray(data) ? data : data?.reports || []);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "加载失败"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div style={{ color: "var(--text-secondary)" }}>加载中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8 text-center">
        <p style={{ color: "var(--danger)" }}>{error}</p>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <h1 className="text-xl font-semibold mb-6">历史报告</h1>

      {reports.length === 0 ? (
        <div className="text-center py-12">
          <p className="mb-4" style={{ color: "var(--text-secondary)" }}>
            暂无报告
          </p>
          <Link
            to="/upload"
            style={{
              backgroundColor: "var(--accent)",
              color: "#fff",
              borderRadius: "8px",
              padding: "10px 24px",
              textDecoration: "none",
            }}
            className="text-sm"
          >
            上传交割单
          </Link>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {reports.map((report) => (
            <Link
              key={report.id}
              to={`/report/${report.id}`}
              style={{
                backgroundColor: "var(--bg-secondary)",
                border: "1px solid var(--border)",
                borderRadius: "12px",
                textDecoration: "none",
                color: "var(--text-primary)",
              }}
              className="p-4 block hover:border-[var(--accent)] transition-colors"
            >
              <div className="flex justify-between items-center">
                <div>
                  <div className="font-medium flex items-center gap-2">
                    {report.filename ? (
                      <span style={{ color: "var(--text-secondary)" }}>📄 {report.filename}</span>
                    ) : (
                      report.title || `报告 ${report.id.slice(0, 8)}`
                    )}
                  </div>
                  {report.created_at && (
                    <div className="text-xs mt-1" style={{ color: "var(--text-secondary)" }}>
                      {new Date(report.created_at).toLocaleString("zh-CN")}
                    </div>
                  )}
                </div>
                <div style={{ color: "var(--accent)" }} className="text-sm">
                  查看 →
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
