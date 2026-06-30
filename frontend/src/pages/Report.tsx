import { useState, useEffect, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { useReport } from "../hooks/useAnalysis";
import { downloadReport } from "../api/report";
import { checkCaseLibraryStatus, contributeToCaseLibrary } from "../api/caseLibrary";
import ReactMarkdown from "react-markdown";
import { Card, Button, LoadingSpinner, EmptyState } from "../components/ui";
import { useToast } from "../context/ToastContext";

export default function Report() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, error } = useReport(id);
  const toast = useToast();
  const [consentState, setConsentState] = useState<"loading" | "show" | "done">("loading");

  const handleDownload = async () => {
    if (!id) return;
    try {
      const blob = await downloadReport(id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `交易诊断报告_${id.substring(0, 8)}.md`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch {
      toast.addToast("error", "下载报告失败");
    }
  };

  // Check case library consent status once report data is available
  useEffect(() => {
    if (!data || error) return;
    let cancelled = false;
    checkCaseLibraryStatus()
      .then((status) => {
        if (cancelled) return;
        setConsentState(status.has_consented ? "done" : "show");
      })
      .catch(() => {
        if (cancelled) return;
        setConsentState("done");
      });
    return () => {
      cancelled = true;
    };
  }, [data, error]);

  const handleContribute = useCallback(async () => {
    try {
      await contributeToCaseLibrary(true, data?.analysis_id);
    } catch {
      // silently fail — not blocking the user
    }
    setConsentState("done");
  }, [data?.analysis_id]);

  const handleDecline = useCallback(async () => {
    try {
      await contributeToCaseLibrary(false);
    } catch {
      // silently fail
    }
    setConsentState("done");
  }, []);

  if (isLoading) {
    return <LoadingSpinner text="加载报告..." />;
  }

  if (error || !data) {
    return (
      <EmptyState
        icon="📄"
        message="该报告不存在或已被删除"
        action={
          <Link to="/history">
            <Button>查看历史报告</Button>
          </Link>
        }
      />
    );
  }

  const handleCopy = async () => {
    if (!data?.report_content) return;
    try {
      await navigator.clipboard.writeText(data.report_content);
      toast.addToast("success", "报告已复制到剪贴板");
    } catch {
      toast.addToast("error", "复制失败，请手动选择文本");
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">交易行为诊断书</h1>
        <div className="flex items-center gap-2">
          {/* C2.4: 返回 is primary (context switch), 下载/复制 are secondary */}
          <Link to={`/analysis/${data.analysis_id}`} className="no-underline">
            <Button variant="primary">返回分析面板</Button>
          </Link>
          <Button variant="outline" onClick={handleCopy}>复制全文</Button>
          <Button variant="outline" onClick={handleDownload}>下载报告</Button>
        </div>
      </div>

      {data.validation_passed === false && (
        <div className="mb-6 rounded-lg border border-warning bg-warning/10 p-4 text-sm text-warning">
          ⚠️ 警告：数据量较少或质量较低，报告仅供参考
        </div>
      )}

      {/* C2.1: chapter TOC — extract ## and ### headings from the markdown */}
      {(() => {
        type Heading = { level: number; text: string };
        const headings: Heading[] = (data.report_content || "")
          .split("\n")
          .map((l: string): Heading | null => {
            const m = /^(#{2,3})\s+(.+)$/.exec(l);
            if (!m) return null;
            // strip bold markers for display, keep text for id
            const text = m[2].replace(/\*\*/g, "").trim();
            return { level: m[1].length, text };
          })
          .filter((h: Heading | null): h is Heading => !!h && !!h.text);
        if (headings.length < 2) return null;
        return (
          <nav aria-label="报告目录" className="mb-4 rounded-lg border border-border bg-bg-secondary/60 p-3">
            <div className="mb-1.5 text-xs font-medium uppercase tracking-wider text-text-secondary">目录</div>
            <ul className="flex flex-wrap gap-x-4 gap-y-1">
              {headings.map((h: Heading) => (
                <li key={h.text}>
                  <a
                    href={`#${encodeURIComponent(h.text)}`}
                    className="text-xs text-accent hover:underline"
                    onClick={(e) => {
                      e.preventDefault();
                      const el = document.getElementById(encodeURIComponent(h.text));
                      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
                    }}
                  >
                    {h.text}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        );
      })()}

      <Card className="p-6 md:p-8">
        <div className="prose prose-invert max-w-none">
          <ReactMarkdown
            components={{
              h1: ({ children, ...props }) => (
                <h1 className="mt-6 mb-3 text-xl font-semibold text-text-primary" {...props}>
                  {children}
                </h1>
              ),
              h2: ({ children, ...props }) => {
                const text = typeof children === "string"
                  ? children
                  : Array.isArray(children)
                    ? children.map((c) => typeof c === "string" ? c : "").join("")
                    : String(children ?? "");
                return (
                  <h2
                    id={encodeURIComponent(text.replace(/\*\*/g, ""))}
                    className="mt-5 mb-2 scroll-mt-20 text-lg font-semibold text-text-primary"
                    {...props}
                  >
                    {children}
                  </h2>
                );
              },
              h3: ({ children, ...props }) => {
                const text = typeof children === "string"
                  ? children
                  : Array.isArray(children)
                    ? children.map((c) => typeof c === "string" ? c : "").join("")
                    : String(children ?? "");
                return (
                  <h3
                    id={encodeURIComponent(text.replace(/\*\*/g, ""))}
                    className="mt-4 mb-2 scroll-mt-20 text-base font-semibold text-text-primary"
                    {...props}
                  >
                    {children}
                  </h3>
                );
              },
              p: ({ children, ...props }) => (
                <p className="mb-3 text-sm leading-relaxed text-text-primary" {...props}>
                  {children}
                </p>
              ),
              ul: ({ children, ...props }) => (
                <ul className="mb-3 space-y-1 pl-5 text-sm text-text-primary" {...props}>
                  {children}
                </ul>
              ),
              li: ({ children, ...props }) => (
                <li className="leading-relaxed text-text-primary" {...props}>
                  {children}
                </li>
              ),
              strong: ({ children, ...props }) => (
                <strong className="text-accent" {...props}>
                  {children}
                </strong>
              ),
              code: ({ children, ...props }) => (
                <code
                  className="rounded bg-bg-tertiary px-1.5 py-0.5 text-xs text-accent"
                  {...props}
                >
                  {children}
                </code>
              ),
            }}
          >
            {data.report_content || ""}
          </ReactMarkdown>
        </div>
      </Card>

      {/* Contribution consent modal */}
      {consentState === "show" && (
        <>
          <div
            className="fixed inset-0 z-[200] animate-fade-in bg-black/50"
            onClick={handleDecline}
          />
          <div
            role="dialog"
            aria-modal="true"
            className="fixed left-1/2 top-1/2 z-[201] w-[90%] max-w-[420px] animate-scale-in rounded-2xl border border-border bg-bg-secondary p-6 shadow-[0_12px_40px_rgba(0,0,0,0.5)] -translate-x-1/2 -translate-y-1/2 md:p-8"
          >
            <div className="mb-4 text-center text-2xl">📊</div>
            <h2 className="mb-2 text-center text-base font-semibold text-text-primary">
              帮助改进 TradeDoctor
            </h2>
            <p className="mb-4 text-center text-sm text-text-secondary">
              您的交易数据能帮助系统变得更聪明。贡献后，您的交割单、分析数据、AI 报告将以完全匿名的方式加入案例库。
            </p>
            <ul className="mb-6 space-y-2">
              {[
                "仅用于分析算法改进",
                "不包含任何个人信息（邮箱/手机）",
                "股票代码保留，账户信息脱敏",
              ].map((item) => (
                <li key={item} className="flex items-start gap-2 text-sm text-text-secondary">
                  <span className="mt-px shrink-0 text-success">✓</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
            <div className="flex flex-col gap-2 md:flex-row md:justify-end">
              <button
                type="button"
                onClick={handleDecline}
                className="cursor-pointer rounded-lg border border-border bg-bg-tertiary px-4 py-2.5 text-sm text-text-primary transition-colors hover:brightness-125 focus-ring"
              >
                不了，谢谢
              </button>
              <button
                type="button"
                onClick={handleContribute}
                className="cursor-pointer rounded-lg border-0 bg-accent px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover focus-ring"
              >
                同意，匿名贡献
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
