import type {
  AgentRunStatus,
  RegionAssessment,
  VulnerableRegionsReport,
  VulnerabilityLevel,
} from "../types/region";

// In development the Vite dev server proxies /agent, /regions and /health to the
// FastAPI backend (see vite.config.ts), so an empty base works out of the box.
// When the frontend is served from a different origin, set VITE_API_BASE to the
// backend URL (e.g. http://localhost:8000).
const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // non-JSON error body — fall back to status text
    }
    throw new Error(detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  /** Trigger a new agent run (background task). */
  runAgent: () => request<AgentRunStatus>("/agent/run", { method: "POST" }),

  /** Poll the current agent run status. */
  getAgentStatus: () => request<AgentRunStatus>("/agent/status"),

  /** Fetch the latest report, optionally filtered by min level / country. */
  getVulnerableRegions: (params?: {
    min_level?: VulnerabilityLevel;
    country?: string;
  }) => {
    const query = new URLSearchParams();
    if (params?.min_level) query.set("min_level", params.min_level);
    if (params?.country) query.set("country", params.country);
    const qs = query.toString();
    return request<VulnerableRegionsReport>(
      `/regions/vulnerable${qs ? `?${qs}` : ""}`,
    );
  },

  /** Fetch a single region assessment by region id. */
  getRegion: (regionId: string) =>
    request<RegionAssessment>(`/regions/${encodeURIComponent(regionId)}`),
};
