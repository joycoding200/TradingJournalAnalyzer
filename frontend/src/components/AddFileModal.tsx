import { useState, useEffect, useRef } from "react";
import FileDropzone from "./FileDropzone";
import { uploadFile, confirmFormat, importTrades } from "../api/upload";
import { linkFilesToAnalysis } from "../api/analysis";
import { useToast } from "../context/ToastContext";

interface Props {
  analysisId: string;
  onClose: () => void;
  onSuccess: () => void;
}

export default function AddFileModal({ analysisId, onClose, onSuccess }: Props) {
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const toast = useToast();
  // Refs for focus-trap + restore
  const dialogRef = useRef<HTMLDivElement>(null);
  const cancelBtnRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  // Focus trap + ESC + scroll lock — mirrors ConfirmContext behavior
  useEffect(() => {
    previouslyFocused.current = document.activeElement as HTMLElement;
    cancelBtnRef.current?.focus();
    const dialog = dialogRef.current;
    if (!dialog) return;

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !loading) {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key === "Tab") {
        const focusables = dialog.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input, [tabindex]:not([tabindex="-1"])'
        );
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = prevOverflow;
      previouslyFocused.current?.focus();
    };
  }, [loading, onClose]);

  const processFile = async (file: File) => {
    setLoading(true);
    try {
      setStatus("正在上传文件...");
      const result = await uploadFile(file);
      const formats = result.detected_formats || [];
      if (formats.length === 0) {
        toast.addToast("warning", "无法识别文件格式");
        setLoading(false);
        return;
      }

      const sourceType = formats[0].source_type;
      setStatus("正在解析交易记录...");
      await confirmFormat(result.raw_file_id, sourceType);

      setStatus("正在导入交易记录...");
      const importResult = await importTrades(result.raw_file_id);
      const { imported_count, skipped_count } = importResult;

      if (skipped_count > 0) {
        toast.addToast(
          "info",
          `已导入 ${imported_count} 笔交易，跳过 ${skipped_count} 笔重复记录`
        );
      }

      setStatus("正在添加到分析...");
      await linkFilesToAnalysis(analysisId, [result.raw_file_id]);

      toast.addToast("success", "文件已添加到分析");
      onSuccess();
      onClose();
    } catch (err) {
      toast.addToast("error", err instanceof Error ? err.message : "添加失败");
      setLoading(false);
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-[200] animate-fade-in bg-black/50"
        onClick={loading ? undefined : onClose}
      />
      {/* Dialog */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="添加交割单"
        className="fixed left-1/2 top-1/2 z-[201] w-[90%] max-w-[440px] animate-scale-in rounded-2xl border border-border bg-bg-secondary p-6 shadow-[0_12px_40px_rgba(0,0,0,0.5)]"
        style={{ transform: "translate(-50%, -50%)" }}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-text-primary">添加交割单</h2>
          <button
            ref={cancelBtnRef}
            type="button"
            onClick={onClose}
            disabled={loading}
            className="border-0 bg-transparent p-[2px_6px] text-lg text-text-secondary transition-opacity hover:text-text-primary focus-ring disabled:opacity-30"
          >
            ✕
          </button>
        </div>

        {!loading ? (
          <FileDropzone onFile={processFile} loading={false} />
        ) : (
          <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border py-8">
            <span className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            <span className="text-sm text-text-secondary">{status}</span>
          </div>
        )}

        <p className="mt-3 text-xs text-text-secondary">
          支持 .csv .xlsx .xls 格式，新文件的交易记录将合并到当前分析中。
        </p>
      </div>
    </>
  );
}
