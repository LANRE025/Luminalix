import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type {
  IngestionRunStatus,
  IngestionRunStatusValue,
  IngestionSourceInfo,
} from "../types/region";

const POLL_INTERVAL_MS = 2000;

export function statusBadgeClasses(status: IngestionRunStatusValue): string {
  switch (status) {
    case "complete":
      return "bg-green-100 text-green-700 border-green-200";
    case "error":
      return "bg-red-100 text-red-700 border-red-200";
    case "running":
      return "bg-blue-100 text-blue-700 border-blue-200";
    case "idle":
      return "bg-slate-100 text-slate-500 border-slate-200";
  }
}

function formatTimestamp(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString();
}

export default function DataSourcesPanel() {
  const [sources, setSources] = useState<IngestionSourceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Per-source in-flight state (source name -> running status poll).
  const [running, setRunning] = useState<Record<string, IngestionRunStatus>>({});
  const timersRef = useRef<Record<string, number | null>>({});

  const stopPolling = useCallback((sourceName: string) => {
    const timer = timersRef.current[sourceName];
    if (timer !== null && timer !== undefined) {
      window.clearInterval(timer);
      timersRef.current[sourceName] = null;
    }
  }, []);

  const loadSources = useCallback(async () => {
    setLoading(true);
    try {
      const next = await api.getIngestionSources();
      setSources(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data sources");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSources();
    return () => {
      for (const name of Object.keys(timersRef.current)) stopPolling(name);
    };
  }, [loadSources, stopPolling]);

  const handleReingest = useCallback(
    async (sourceName: string) => {
      setError(null);
      try {
        await api.runIngestion(sourceName);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to start re-ingestion");
        return;
      }
      // Poll status until the run leaves the "running" state, then refresh
      // the source list to pick up the new status/timestamp.
      timersRef.current[sourceName] = window.setInterval(async () => {
        let status: IngestionRunStatus;
        try {
          status = await api.getIngestionStatus(sourceName);
        } catch {
          return; // transient network error — keep polling
        }
        setRunning((prev) => ({ ...prev, [sourceName]: status }));
        if (status.status === "running") return;

        stopPolling(sourceName);
        setRunning((prev) => {
          const next = { ...prev };
          delete next[sourceName];
          return next;
        });
        await loadSources();
      }, POLL_INTERVAL_MS);
    },
    [loadSources, stopPolling],
  );

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold">Data sources</h2>
        <p className="text-sm text-slate-500">
          Manually re-ingest a source into SQLite and DataHub. Nothing runs
          automatically.
        </p>
        <button
          type="button"
          onClick={() => void loadSources()}
          className="ml-auto rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Refresh
        </button>
      </div>

      {loading && <p className="py-10 text-center text-slate-500">Loading sources…</p>}

      {!loading && error && sources.length === 0 && (
        <div className="rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <p>{error}</p>
          <button
            type="button"
            onClick={() => void loadSources()}
            className="mt-2 font-medium underline"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && sources.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2.5">Source</th>
                <th className="px-4 py-2.5">Last ingested</th>
                <th className="px-4 py-2.5">Status</th>
                <th className="px-4 py-2.5">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {sources.map((source) => {
                const active = running[source.name];
                const status: IngestionRunStatusValue = active
                  ? active.status
                  : (source.last_status ?? "idle");
                const timestamp = active
                  ? active.completed_at
                  : source.last_completed_at;
                return (
                  <tr key={source.name} className="align-top">
                    <td className="px-4 py-3">
                      <p className="font-medium">{source.display_name}</p>
                      <p className="text-xs text-slate-500">{source.description}</p>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-slate-600">
                      {formatTimestamp(timestamp)}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${statusBadgeClasses(
                          status,
                        )}`}
                      >
                        {status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => void handleReingest(source.name)}
                        disabled={status === "running"}
                        className={`rounded-md px-4 py-2 text-sm font-medium text-white transition-colors ${
                          status === "running"
                            ? "cursor-not-allowed bg-slate-400"
                            : "bg-emerald-600 hover:bg-emerald-700"
                        }`}
                      >
                        {status === "running" ? (
                          <span className="inline-flex items-center gap-2">
                            <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                            Re-ingesting…
                          </span>
                        ) : (
                          "Reingest"
                        )}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {error && sources.length > 0 && (
        <p className="mt-2 text-right text-xs text-red-600">{error}</p>
      )}
    </section>
  );
}
