import { apiGet, apiPost } from "./client";

export async function runAnalysis(date_start: string, date_end: string, raw_file_id = "", filename = ""): Promise<any> {
  return apiPost("/api/analysis/run", { date_start, date_end, raw_file_id, filename });
}

export async function getStats(id: string): Promise<any> {
  return apiGet(`/api/analysis/${id}/stats`);
}

export async function getInsight(id: string): Promise<any> {
  return apiGet(`/api/analysis/${id}/insight`);
}

export async function getWhatIf(id: string): Promise<any> {
  return apiGet(`/api/analysis/${id}/whatif`);
}
