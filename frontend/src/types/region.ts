// TypeScript types mirroring the backend Pydantic schemas exactly
// (see backend/app/models/schemas.py — keep these two files in sync).

export type VulnerabilityLevel = "Low" | "Moderate" | "High";
export type Confidence = "Low" | "Medium" | "High";
export type AgentRunStatusValue = "idle" | "running" | "complete" | "error";

export interface RegionAssessment {
  region: string;
  country: string;
  disease: string | null;
  vulnerability_level: VulnerabilityLevel;
  justification: string;
  confidence: Confidence;
  key_signals: string[];
  days_stale: number;
  flagged_at: string; // ISO 8601 timestamp
}

export interface VulnerableRegionsReport {
  generated_at: string; // ISO 8601 timestamp
  total_regions_evaluated: number;
  total_flagged: number;
  regions: RegionAssessment[];
}

export interface AgentRunStatus {
  status: AgentRunStatusValue;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
}
