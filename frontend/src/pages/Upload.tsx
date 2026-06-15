import { useState } from "react";
import { useNavigate } from "react-router-dom";
import FileDropzone from "../components/FileDropzone";
import FormatSelector from "../components/FormatSelector";
import { uploadFile, confirmFormat, importTrades } from "../api/upload";
import { runAnalysis } from "../api/analysis";

interface FormatOption {
  source_type: string;
  asset_type: string;
  score: number;
}

export default function Upload() {
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState("");
  const [rawFileId, setRawFileId] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const [formats, setFormats] = useState<FormatOption[]>([]);
  const [parsedData, setParsedData] = useState<Record<string, unknown>[]>([]);
  const navigate = useNavigate();

  const autoProcess = async (fileId: string, sourceType: string, fileName: string) => {
    // Confirm format
    setStatusText("正在解析交易记录...");
    const confirmed = await confirmFormat(fileId, sourceType);
    const trades = confirmed.trades || [];
    setParsedData(trades);

    // Import trades
    setStatusText("正在导入交易记录...");
    await importTrades(fileId);

    // Run analysis with actual trade date range
    setStatusText("正在运行分析...");
    const dates = trades
      .map((t: any) => t.datetime)
      .filter(Boolean)
      .sort();
    const today = new Date().toISOString().split("T")[0];
    const dateStart = dates[0]?.split("T")[0] || "2020-01-01";
    const dateEnd = dates[dates.length - 1]?.split("T")[0] || today;
    const analysis = await runAnalysis(dateStart, dateEnd, fileId, fileName);
    navigate(`/analysis/${analysis.analysis_id}`);
  };

  const handleFile = async (file: File) => {
    setLoading(true);
    setStatusText("正在上传文件...");
    try {
      const result = await uploadFile(file);
      const detectedFormats = result.detected_formats || [];
      setRawFileId(result.raw_file_id);
      setFileName(file.name);
      setFormats(detectedFormats);

      if (detectedFormats.length > 0 && detectedFormats[0].score >= 0.7) {
        // Auto-process: skip format selection
        await autoProcess(result.raw_file_id, detectedFormats[0].source_type, file.name);
      } else if (detectedFormats.length > 0) {
        // Low confidence: let user pick format
        setLoading(false);
        setStatusText("");
      } else {
        setLoading(false);
        alert("无法识别文件格式，请确认文件内容正确");
      }
    } catch (err) {
      setLoading(false);
      alert(err instanceof Error ? err.message : "上传失败");
    }
  };

  const handleConfirm = async (sourceType: string) => {
    setLoading(true);
    try {
      await autoProcess(rawFileId, sourceType, fileName);
    } catch (err) {
      setLoading(false);
      alert(err instanceof Error ? err.message : "处理失败");
    }
  };

  // Show format selector only when confidence is low
  if (formats.length > 0 && formats[0].score < 0.7) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-xl font-semibold mb-6">上传交割单</h1>
        <FormatSelector formats={formats} onConfirm={handleConfirm} loading={loading} />
      </div>
    );
  }

  // Show error state when no formats detected (and not loading)
  if (formats.length === 0 && !loading && rawFileId) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <h1 className="text-xl font-semibold mb-6">上传交割单</h1>
        <FileDropzone onFile={handleFile} loading={false} />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <h1 className="text-xl font-semibold mb-6">上传交割单</h1>
      <FileDropzone onFile={handleFile} loading={loading} />
      {loading && statusText && (
        <div className="text-center mt-6" style={{ color: "var(--text-secondary)" }}>
          <div className="inline-block w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin mr-2 align-middle" />
          {statusText}
        </div>
      )}
    </div>
  );
}
