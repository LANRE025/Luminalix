import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type {
  RegionAssessment,
  VulnerableRegionsReport,
  VulnerabilityLevel,
} from "../types/region";
import { levelBadgeClasses } from "./badges";

interface RegionsListProps {
  report: VulnerableRegionsReport | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}

type SortKey = "vulnerability_level" | "days_stale" | "country" | "region";

const LEVEL_ORDER: Record<VulnerabilityLevel, number> = {
  High: 3,
  Moderate: 2,
  Low: 1,
};

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "region", label: "Region" },
  { key: "country", label: "Country" },
  { key: "vulnerability_level", label: "Level" },
  { key: "days_stale", label: "Survey age" },
  { key: "region", label: "Justification" },
];

export default function RegionsList({ report, loading, error, onRefresh }: RegionsListProps) {
  const navigate = useNavigate();
  const [countryFilter, setCountryFilter] = useState<string>("");
  const [levelFilter, setLevelFilter] = useState<VulnerabilityLevel | "All">("All");
  const [sortKey, setSortKey] = useState<SortKey>("vulnerability_level");
  const [sortAsc, setSortAsc] = useState(false);

  const regions = useMemo(() => report?.regions ?? [], [report]);
  const countries = useMemo(
    () => Array.from(new Set(regions.map((r) => r.country))).sort(),
    [regions],
  );

  const filtered = useMemo(() => {
    let rows = regions;
    if (countryFilter) rows = rows.filter((r) => r.country === countryFilter);
    if (levelFilter !== "All") rows = rows.filter((r) => r.vulnerability_level === levelFilter);

    const dir = sortAsc ? 1 : -1;
    return [...rows].sort((a, b) => {
      switch (sortKey) {
        case "vulnerability_level": {
          const cmp = LEVEL_ORDER[a.vulnerability_level] - LEVEL_ORDER[b.vulnerability_level];
          return cmp !== 0 ? cmp * dir : (a.days_stale - b.days_stale) * dir;
        }
        case "days_stale":
          return (a.days_stale - b.days_stale) * dir;
        case "country":
          return a.country.localeCompare(b.country) * dir;
        case "region":
          return a.region.localeCompare(b.region) * dir;
      }
    });
  }, [regions, countryFilter, levelFilter, sortKey, sortAsc]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortAsc((v) => !v);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  const noReportYet = report !== null && report.total_regions_evaluated === 0;

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold">
          Vulnerable regions
          {report && !noReportYet && (
            <span className="ml-2 text-sm font-normal text-slate-500">
              {report.total_flagged} of {report.total_regions_evaluated} regions flagged
            </span>
          )}
        </h2>
        {report && !noReportYet && (
          <div className="ml-auto flex flex-wrap items-center gap-2 text-sm">
            <select
              aria-label="Filter by country"
              value={countryFilter}
              onChange={(e) => setCountryFilter(e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm focus:border-emerald-500 focus:outline-none"
            >
              <option value="">All countries</option>
              {countries.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
            <select
              aria-label="Filter by level"
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value as VulnerabilityLevel | "All")}
              className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm focus:border-emerald-500 focus:outline-none"
            >
              <option value="All">All levels</option>
              <option value="High">High</option>
              <option value="Moderate">Moderate</option>
              <option value="Low">Low</option>
            </select>
          </div>
        )}
      </div>

      {loading && <p className="py-10 text-center text-slate-500">Loading report…</p>}

      {!loading && error && !report && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <p>{error}</p>
          <button type="button" onClick={onRefresh} className="mt-2 font-medium underline">
            Retry
          </button>
        </div>
      )}

      {!loading && report && noReportYet && (
        <div className="rounded-md border border-slate-200 bg-white p-8 text-center text-slate-500">
          No report yet. Click{" "}
          <span className="font-medium text-slate-700">Run vulnerability scan</span> above to
          trigger the agent.
        </div>
      )}

      {report && !noReportYet && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                {COLUMNS.slice(0, 4).map((col) => (
                  <th key={col.key} className="px-4 py-2.5">
                    <button
                      type="button"
                      onClick={() => toggleSort(col.key)}
                      className="inline-flex items-center gap-1 hover:text-slate-900"
                    >
                      {col.label}
                      {sortKey === col.key && <span>{sortAsc ? "↑" : "↓"}</span>}
                    </button>
                  </th>
                ))}
                <th className="px-4 py-2.5">Justification</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((region) => (
                <tr
                  key={region.region}
                  onClick={() => navigate(`/regions/${encodeURIComponent(region.region)}`)}
                  className="cursor-pointer transition-colors hover:bg-slate-50"
                >
                  <td className="px-4 py-3 font-medium">{region.region}</td>
                  <td className="px-4 py-3">{region.country}</td>
                  <td className="px-4 py-3">
                    <LevelBadge region={region} />
                  </td>
                  <td className="px-4 py-3">{region.days_stale} days</td>
                  <td className="max-w-xs px-4 py-3 text-xs text-slate-500">
                    <span className="line-clamp-2">{region.justification}</span>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                    No regions match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function LevelBadge({ region }: { region: RegionAssessment }) {
  return (
    <span
      className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${levelBadgeClasses(
        region.vulnerability_level,
      )}`}
    >
      {region.vulnerability_level}
    </span>
  );
}
