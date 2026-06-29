import { LoadingSpinner, ErrorBox } from "../../components/ui";
import StatsCards from "../../components/StatsCards";

interface StatsTabProps {
  stats: {
    isLoading: boolean;
    error: Error | null;
    data: any;
  };
  /**
   * Open the in-page AddFileModal (preferred for adding files to an
   * existing analysis — keeps the user on this page and invalidates
   * React Query automatically).
   */
  onAddFile?: () => void;
}

export default function StatsTab({ stats, onAddFile }: StatsTabProps) {
  if (stats.isLoading) return <LoadingSpinner text="加载统计数据..." />;
  if (stats.error) return <ErrorBox message="加载失败" />;
  if (stats.data)
    return (
      <StatsCards stats={stats.data} onAddFile={onAddFile} />
    );
  return null;
}
