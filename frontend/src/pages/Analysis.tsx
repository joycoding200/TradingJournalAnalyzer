import { useParams, useNavigate } from "react-router-dom";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useStats, useInsight, useWhatIf, useGenerateReport, useCheckReport } from "../hooks/useAnalysis";
import { Button, InlineSpinner } from "../components/ui";
import AddFileModal from "../components/AddFileModal";
import { useToast } from "../context/ToastContext";
import StatsTab from "./tabs/StatsTab";
import InsightTab from "./tabs/InsightTab";
import WhatIfTab from "./tabs/WhatIfTab";

type Tab = "stats" | "insight" | "whatif";

export default function Analysis() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>("stats");
  const [showAddFile, setShowAddFile] = useState(false);
  const toast = useToast();

  const stats = useStats(id);
  const statsReady = !stats.isLoading && !!stats.data;
  const insight = useInsight(id, statsReady);
  const whatIf = useWhatIf(id, statsReady);
  const genReport = useGenerateReport();
  const checkReport = useCheckReport(id);

  const handleGenerateReport = () => {
    if (!id) return;
    genReport.mutate(id, {
      onSuccess: (data: any) => {
        navigate(`/report/${data.report_id}`);
      },
      onError: (err: Error) => {
        toast.addToast("error", `AI 报告生成失败：${err.message || "请稍后重试"}`);
      },
    });
  };

  const tabs: { key: Tab; label: string; loading?: boolean }[] = [
    { key: "stats", label: "统计概览" },
    { key: "insight", label: "归因分析", loading: statsReady && insight.isLoading },
    { key: "whatif", label: "情景回测（What If）", loading: statsReady && whatIf.isLoading },
  ];

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">分析面板</h1>
          {(stats.data?.filenames && stats.data.filenames.length > 1) ? (
            <div className="mt-1 text-xs text-text-secondary">
              📄 {stats.data.filenames.join(" + ")}
            </div>
          ) : stats.data?.filename ? (
            <div className="mt-1 text-xs text-text-secondary">
              📄 {stats.data.filename}
            </div>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setShowAddFile(true)}>
            + 添加交割单
          </Button>
          <Button
            variant="success"
            onClick={
              checkReport.data?.exists
                ? () => navigate(`/report/${checkReport.data.report_id}`)
                : handleGenerateReport
            }
            disabled={checkReport.isLoading || genReport.isPending}
          >
            {genReport.isPending ? (
              <><InlineSpinner /> 生成中...</>
            ) : checkReport.isLoading ? (
              <><InlineSpinner /> 检查中...</>
            ) : checkReport.data?.exists ? (
              "查看 AI 报告"
            ) : (
              "生成 AI 报告"
            )}
          </Button>
        </div>
      </div>

      <div className="mb-6 flex gap-1 border-b border-border" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={activeTab === tab.key}
            onClick={() => setActiveTab(tab.key)}
            className="tab-btn px-4 py-2.5 text-sm font-medium"
          >
            {tab.label}{tab.loading ? " …" : ""}
          </button>
        ))}
      </div>

      <div className="transition-opacity duration-200">
        {activeTab === "stats" && <StatsTab stats={stats} />}
        {activeTab === "insight" && <InsightTab insight={insight} />}
        {activeTab === "whatif" && <WhatIfTab whatIf={whatIf} />}
      </div>

      {showAddFile && id && (
        <AddFileModal
          analysisId={id}
          onClose={() => setShowAddFile(false)}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["stats", id] });
            queryClient.invalidateQueries({ queryKey: ["insight", id] });
            queryClient.invalidateQueries({ queryKey: ["whatif", id] });
          }}
        />
      )}
    </div>
  );
}
