import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import type { RegionAssessment } from "../types/region";
import { confidenceBadgeClasses, levelBadgeClasses } from "./badges";

export default function RegionDetail() {
  const { regionId } = useParams<{ regionId: string }>();
  const [region, setRegion] = useState<RegionAssessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!regionId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    api
      .getRegion(regionId)
      .then((data) => {
        if (!cancelled) setRegion(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load region");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [regionId]);

  return (
    <div>
      <Link to="/" className="text-sm font-medium text-emerald-700 hover:underline">
        ← Back to vulnerable regions
      </Link>

      {loading && <p className="py-10 text-center text-slate-500">Loading region…</p>}

      {!loading && error && (
        <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error}
        </div>
      )}

      {!loading && region && (
        <article className="mt-4">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-2xl font-semibold">{region.region}</h2>
              <p className="text-sm text-slate-500">
                {region.country} · flagged {formatTimestamp(region.flagged_at)} · survey data{" "}
                {region.days_stale} days stale
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`rounded-full border px-3 py-1 text-sm font-medium ${levelBadgeClasses(
                  region.vulnerability_level,
                )}`}
              >
                {region.vulnerability_level} vulnerability
              </span>
              <span
                className={`rounded-full border px-3 py-1 text-sm font-medium ${confidenceBadgeClasses(
                  region.confidence,
                )}`}
              >
                {region.confidence} confidence
              </span>
            </div>
          </div>

          <div className="space-y-6">
            <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Why this region was flagged
              </h3>
              <p className="text-lg leading-relaxed text-slate-800">{region.justification}</p>
            </section>

            <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
              <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Key signals
              </h3>
              {region.key_signals.length > 0 ? (
                <ul className="list-disc space-y-1.5 pl-5 text-slate-700">
                  {region.key_signals.map((signal) => (
                    <li key={signal}>{signal}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-slate-400">No key signals recorded.</p>
              )}
            </section>

            <section className="rounded-lg border border-slate-200 bg-white p-5 text-sm shadow-sm">
              <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Assessment metadata
              </h3>
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <div>
                  <dt className="text-slate-500">Region</dt>
                  <dd className="font-medium">{region.region}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Country</dt>
                  <dd className="font-medium">{region.country}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Survey age</dt>
                  <dd className="font-medium">{region.days_stale} days</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Flagged at</dt>
                  <dd className="font-medium">{formatTimestamp(region.flagged_at)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Vulnerability</dt>
                  <dd className="font-medium">{region.vulnerability_level}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Confidence</dt>
                  <dd className="font-medium">{region.confidence}</dd>
                </div>
              </dl>
            </section>
          </div>
        </article>
      )}
    </div>
  );
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}
