import { apiGet, apiPost } from "./client";

export async function checkCaseLibraryStatus(): Promise<{ has_consented: boolean }> {
  return apiGet("/api/case-library/status");
}

export async function contributeToCaseLibrary(
  consent: boolean,
  analysisId?: string
): Promise<any> {
  return apiPost("/api/case-library/contribute", {
    consent,
    ...(consent ? { analysis_id: analysisId } : {}),
  });
}
