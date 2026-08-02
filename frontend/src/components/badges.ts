import type { Confidence, VulnerabilityLevel } from "../types/region";

// Color-coding: High=red, Moderate/Medium=amber, Low=green.
export function levelBadgeClasses(level: VulnerabilityLevel): string {
  switch (level) {
    case "High":
      return "bg-red-100 text-red-700 border-red-200";
    case "Moderate":
      return "bg-amber-100 text-amber-700 border-amber-200";
    case "Low":
      return "bg-green-100 text-green-700 border-green-200";
  }
}

export function confidenceBadgeClasses(confidence: Confidence): string {
  switch (confidence) {
    case "High":
      return "bg-red-100 text-red-700 border-red-200";
    case "Medium":
      return "bg-amber-100 text-amber-700 border-amber-200";
    case "Low":
      return "bg-green-100 text-green-700 border-green-200";
  }
}
