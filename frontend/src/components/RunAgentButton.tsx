import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { AgentRunStatus } from "../types/region";

interface RunAgentButtonProps {
  onComplete: () => void | Promise<void>;
}

const POLL_INTERVAL_MS = 2000;

export function RunAgentButton({ onComplete }: RunAgentButtonProps) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const handleClick = useCallback(async () => {
    setError(null);
    setRunning(true);
    try {
      await api.runAgent();
      timerRef.current = window.setInterval(async () => {
        let status: AgentRunStatus;
        try {
          status = await api.getAgentStatus();
        } catch {
          return; // transient network error — keep polling
        }
        if (status.status === "running") return;

        stopPolling();
        setRunning(false);
        if (status.status === "error") {
          setError(status.error_message ?? "Agent run failed");
          return;
        }
        await onComplete();
      }, POLL_INTERVAL_MS);
    } catch (err) {
      setRunning(false);
      setError(err instanceof Error ? err.message : "Failed to start agent run");
    }
  }, [onComplete, stopPolling]);

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={() => void handleClick()}
        disabled={running}
        className={`rounded-md px-4 py-2 text-sm font-medium text-white transition-colors ${
          running
            ? "cursor-not-allowed bg-slate-400"
            : "bg-emerald-600 hover:bg-emerald-700"
        }`}
      >
        {running ? (
          <span className="inline-flex items-center gap-2">
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
            Running agent…
          </span>
        ) : (
          "Run vulnerability scan"
        )}
      </button>
      {error && <p className="max-w-xs text-right text-xs text-red-600">{error}</p>}
    </div>
  );
}
