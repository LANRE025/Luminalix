import { useEffect, useState } from "react";
import { Link, Route, Routes } from "react-router-dom";
import { api } from "./api/client";
import { RunAgentButton } from "./components/RunAgentButton";
import RegionsList from "./components/RegionsList";
import RegionDetail from "./components/RegionDetail";
import type { VulnerableRegionsReport } from "./types/region";

export default function App() {
  const [report, setReport] = useState<VulnerableRegionsReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadReport = async () => {
    setLoading(true);
    try {
      const next = await api.getVulnerableRegions({ min_level: "Low" });
      setReport(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load report");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadReport();
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-4 px-4 py-4">
          <Link to="/" className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-600 text-sm font-bold text-white">
              OVS
            </span>
            <div>
              <h1 className="text-lg font-semibold leading-tight">
                Outbreak Vulnerability Sentinel
              </h1>
              <p className="text-xs text-slate-500">
                Survey staleness x admissions trends x resource allocation
              </p>
            </div>
          </Link>
          <RunAgentButton onComplete={loadReport} />
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        <Routes>
          <Route
            path="/"
            element={
              <RegionsList
                report={report}
                loading={loading}
                error={error}
                onRefresh={loadReport}
              />
            }
          />
          <Route path="/regions/:regionId" element={<RegionDetail />} />
        </Routes>
      </main>
    </div>
  );
}
