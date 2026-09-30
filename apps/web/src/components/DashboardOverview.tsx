"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ArrowUpRight, ArrowDownRight, Building2, FileSearch, Globe2, RefreshCw, Sparkles, Tags } from "lucide-react";
import {
  ApiError, companiesApi, dashboardApi, getSystemInfo, ingestionApi, intelligenceApi, sourcesApi, topicsApi, workspaceApi,
  type DashboardOverviewResponse, type FocusEntity, type IntelligenceSignal, type KeyCount, type RecentJob, type Source,
} from "@/lib/api";
import { DistributionSkeleton, FocusListSkeleton, SignalListSkeleton, TimelineListSkeleton } from "@/components/loading/DashboardSkeleton";

const SIGNAL_TYPE_LABELS: Record<string, string> = {
  product: "Product", competitor: "Competitor", funding: "Funding", partnership: "Partnership",
  acquisition: "Acquisition", leadership: "Leadership", regulation: "Regulation",
  technology: "Technology", market: "Market", pricing: "Pricing", risk: "Risk", other: "Other",
};

function toneFor(sentiment: IntelligenceSignal["sentiment"]): "green" | "coral" | "amber" {
  if (sentiment === "positive") return "green";
  if (sentiment === "negative") return "coral";
  return "amber";
}

function formatShortDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatCount(value: number | undefined): string {
  return value === undefined ? "—" : String(value).padStart(2, "0");
}

// -- DEPLOYMENT-TRANSITION COMPATIBILITY (temporary) --------------------------------
//
// Vercel deploys this frontend automatically on merge; the Lambda backend is deployed
// manually. That means there is a real window where this build is live but production
// Lambda does not yet expose GET /api/v1/dashboard/overview. Falling back to the old
// seven-request loader ONLY on a genuine 404 keeps the dashboard usable during that
// window without masking a real failure (any other error -- network, 500, auth, timeout --
// must stay a visible failure, not silently trigger this path).
//
// Remove this whole block once the new endpoint is confirmed live in production.

function countEntries<T>(items: T[], keyOf: (item: T) => string): KeyCount[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const key = keyOf(item);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([key, count]) => ({ key, count }));
}

function focusEntities(
  signals: IntelligenceSignal[], field: "company_id" | "topic_id", namesById: Record<string, string>, limit = 3,
): FocusEntity[] {
  const counts = new Map<string, number>();
  for (const signal of signals) {
    const id = signal[field];
    if (id) counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, limit)
    .map(([id, count]) => ({ id, name: namesById[id] ?? "Unknown", count }));
}

async function loadLegacyOverview(): Promise<DashboardOverviewResponse> {
  const [systemInfo, summary, signalsResult, jobsResult, sources, companies, topics] = await Promise.all([
    getSystemInfo(), workspaceApi.summary(), intelligenceApi.listSignals(), ingestionApi.listJobs(),
    sourcesApi.list(), companiesApi.list(), topicsApi.list(),
  ]);
  const signals = signalsResult.items;
  const sourcesById = Object.fromEntries(sources.items.map((source: Source) => [source.id, source]));
  const companiesById = Object.fromEntries(companies.items.map((company) => [company.id, company.name]));
  const topicsById = Object.fromEntries(topics.items.map((topic) => [topic.id, topic.name]));

  const priority_signals = [...signals]
    .sort((a, b) => b.importance_score - a.importance_score || b.analyzed_at.localeCompare(a.analyzed_at))
    .slice(0, 3);
  const latest_signals = [...signals].sort((a, b) => b.analyzed_at.localeCompare(a.analyzed_at)).slice(0, 3);

  const recent_jobs: RecentJob[] = [...jobsResult.items]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 5)
    .map((job) => ({ ...job, source_name: sourcesById[job.source_id]?.name ?? "Unknown source" }));

  return {
    providers: { llm_provider: systemInfo.llm_provider, embedding_provider: systemInfo.embedding_provider },
    summary,
    priority_signals,
    latest_signals,
    signal_type_counts: countEntries(signals, (signal) => signal.signal_type ?? "other"),
    sentiment_counts: countEntries(signals, (signal) => signal.sentiment ?? "neutral"),
    recent_jobs,
    focus_companies: focusEntities(signals, "company_id", companiesById),
    focus_topics: focusEntities(signals, "topic_id", topicsById),
  };
}

// -- End deployment-transition compatibility ----------------------------------------

export function DashboardOverview() {
  const [connection, setConnection] = useState<"checking" | "connected" | "unavailable">("checking");
  const [data, setData] = useState<DashboardOverviewResponse | null>(null);
  const [error, setError] = useState("");
  const [today, setToday] = useState<string | null>(null);

  const load = useCallback(async () => {
    setConnection("checking");
    setError("");
    try {
      const result = await dashboardApi.overview();
      setData(result);
      setConnection("connected");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 404) {
        try {
          const legacy = await loadLegacyOverview();
          setData(legacy);
          setConnection("connected");
          return;
        } catch (legacyCause) {
          setConnection("unavailable");
          setError(legacyCause instanceof ApiError ? legacyCause.message : "Could not load the dashboard.");
          return;
        }
      }
      setConnection("unavailable");
      setError(cause instanceof ApiError ? cause.message : "Could not load the dashboard.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setToday(new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric", year: "numeric" }).toUpperCase());
  }, []);

  const loading = connection === "checking";
  const unavailable = connection === "unavailable";
  const isMock = data ? data.providers.llm_provider === "mock" : true;

  const signalTypeCounts = data?.signal_type_counts ?? [];
  const sentimentCounts = data?.sentiment_counts ?? [];
  const maxSignalTypeCount = Math.max(1, ...signalTypeCounts.map((item) => item.count));
  const maxSentimentCount = Math.max(1, ...sentimentCounts.map((item) => item.count));

  return (
    <div className="dashboard-page">
      <section className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-rule" />{today ?? "TODAY"}</div>
          <h1>Good morning, Jordan<span>.</span></h1>
          <p className="heading-subtitle">Your market, in focus.</p>
        </div>
        <div className={`connection-pill connection-${connection}`}>
          <span className="connection-dot" />
          {connection === "connected" ? "API connected" : connection === "checking" ? "Connecting" : "API unavailable"}
        </div>
      </section>

      <section className="metric-grid" aria-label="Workspace monitoring summary">
        <Metric label="Companies monitored" value={formatCount(data?.summary.companies)} change="In this workspace" icon={<Building2 size={17} />} tone="green" />
        <Metric label="Topics tracked" value={formatCount(data?.summary.topics)} change="In this workspace" icon={<Tags size={17} />} tone="amber" />
        <Metric label="Active watchlists" value={formatCount(data?.summary.active_watchlists)} change={data ? `${data.summary.watchlists} total` : "Loading"} icon={<FileSearch size={17} />} tone="coral" />
        <Metric label="Active sources" value={formatCount(data?.summary.active_sources)} change={data ? `${data.summary.sources} total` : "Loading"} icon={<Globe2 size={17} />} tone="blue" />
      </section>

      {unavailable ? (
        <div className="empty-surface" role="alert">
          <div className="empty-symbol"><RefreshCw size={19} /></div>
          <h2>The dashboard could not load</h2>
          <p>{error || "Vantage API is currently unavailable."}</p>
          <button className="secondary-button" onClick={() => void load()}>
            <RefreshCw size={15} /> Retry
          </button>
        </div>
      ) : (
        <>
          <section className="section-block signal-section">
            <div className="section-heading">
              <div><span className="section-kicker">WHAT MATTERS NOW{isMock ? " · MOCK AI" : ""}</span><h2>Priority signals</h2></div>
              <Link className="text-link" href="/workspace/intelligence">All intelligence <ArrowRight size={15} /></Link>
            </div>
            <div className="signal-list">
              {loading ? (
                <SignalListSkeleton />
              ) : (data?.priority_signals.length ?? 0) === 0 ? (
                <p className="panel-footnote">No analyzed intelligence yet. Analyze a collected document on the Intelligence page.</p>
              ) : (
                data!.priority_signals.map((signal) => (
                  <article className="signal-row" key={signal.id}>
                    <div className={`signal-marker marker-${toneFor(signal.sentiment)}`}><Sparkles size={15} /></div>
                    <div className="signal-main">
                      <span className={`signal-category category-${toneFor(signal.sentiment)}`}>{(signal.signal_type ?? "other").toUpperCase()}</span>
                      <h3>{signal.title}</h3>
                      <p>{signal.executive_summary}</p>
                    </div>
                    <div className="signal-meta"><span className="relevance-score">{Math.round(signal.importance_score * 100)}<small> importance</small></span><span>{formatShortDate(signal.analyzed_at)}</span></div>
                  </article>
                ))
              )}
            </div>
          </section>

          <div className="dashboard-lower-grid">
            <section className="section-block activity-panel">
              <div className="section-heading compact-heading"><div><span className="section-kicker">BY TYPE</span><h2>Signal distribution</h2></div></div>
              <div className="distribution-body">
                {loading ? (
                  <DistributionSkeleton />
                ) : signalTypeCounts.length === 0 ? (
                  <p className="panel-footnote">No analyzed intelligence yet.</p>
                ) : (
                  <div className="distribution-list">
                    {signalTypeCounts.map(({ key, count }) => (
                      <div className="distribution-row" key={key}>
                        <span className="distribution-label">{SIGNAL_TYPE_LABELS[key] ?? key}</span>
                        <div className="distribution-track"><div className="distribution-fill" style={{ width: `${(count / maxSignalTypeCount) * 100}%` }} /></div>
                        <span className="distribution-count">{count}</span>
                      </div>
                    ))}
                  </div>
                )}
                {!loading && sentimentCounts.length > 0 && (
                  <>
                    <p className="distribution-subheading">By sentiment</p>
                    <div className="distribution-list">
                      {sentimentCounts.map(({ key, count }) => (
                        <div className="distribution-row" key={key}>
                          <span className="distribution-label">{key}</span>
                          <div className="distribution-track"><div className={`distribution-fill sentiment-fill-${key}`} style={{ width: `${(count / maxSentimentCount) * 100}%` }} /></div>
                          <span className="distribution-count">{count}</span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </section>

            <section className="section-block timeline-panel">
              <div className="section-heading compact-heading"><div><span className="section-kicker">RECENTLY ANALYZED</span><h2>Latest intelligence</h2></div></div>
              <div className="timeline-list">
                {loading ? (
                  <TimelineListSkeleton label="Loading latest intelligence" />
                ) : (data?.latest_signals.length ?? 0) === 0 ? (
                  <p className="panel-footnote">No analyzed intelligence yet.</p>
                ) : (
                  data!.latest_signals.map((signal) => (
                    <article className="timeline-item" key={signal.id}>
                      <span className="timeline-time">{formatShortDate(signal.analyzed_at)}</span>
                      <div className="timeline-copy"><span>{(signal.signal_type ?? "other").toUpperCase()}</span><h3>{signal.title}</h3><small>{signal.sentiment ?? "neutral"}</small></div>
                    </article>
                  ))
                )}
              </div>
              <div className="panel-footnote">{isMock ? "Mock AI analysis — no real model was called" : "Analyzed intelligence"}</div>
            </section>
          </div>

          <div className="dashboard-lower-grid">
            <section className="section-block activity-panel">
              <div className="section-heading compact-heading"><div><span className="section-kicker">SOURCE MONITOR</span><h2>Recent ingestion activity</h2></div></div>
              <div className="timeline-list">
                {loading ? (
                  <TimelineListSkeleton label="Loading ingestion activity" />
                ) : (data?.recent_jobs.length ?? 0) === 0 ? (
                  <p className="panel-footnote">No ingestion runs yet. Run ingestion from the Sources page.</p>
                ) : (
                  data!.recent_jobs.map((job) => (
                    <article className="timeline-item" key={job.id}>
                      <span className="timeline-time">{formatShortDate(job.created_at)}</span>
                      <div className="timeline-copy">
                        <span>{job.source_name}</span>
                        <h3>
                          {job.status === "completed"
                            ? `${job.documents_created} new document${job.documents_created === 1 ? "" : "s"}`
                            : job.status === "failed" ? "Ingestion failed" : job.status[0].toUpperCase() + job.status.slice(1)}
                        </h3>
                        <small>{job.documents_found} found · {job.pages_failed} failed</small>
                      </div>
                    </article>
                  ))
                )}
              </div>
            </section>

            <section className="section-block timeline-panel">
              <div className="section-heading compact-heading"><div><span className="section-kicker">MONITORED</span><h2>Companies &amp; topics in focus</h2></div></div>
              <div className="focus-columns">
                <div>
                  <span className="section-kicker">TOP COMPANIES</span>
                  {loading ? <FocusListSkeleton /> : (data?.focus_companies.length ?? 0) === 0 ? (
                    <p className="panel-footnote">No company-linked signals yet.</p>
                  ) : (
                    <ul className="focus-list">{data!.focus_companies.map((item) => <li key={item.id}><span>{item.name}</span><span className="count-tag">{item.count}</span></li>)}</ul>
                  )}
                </div>
                <div>
                  <span className="section-kicker">TOP TOPICS</span>
                  {loading ? <FocusListSkeleton /> : (data?.focus_topics.length ?? 0) === 0 ? (
                    <p className="panel-footnote">No topic-linked signals yet.</p>
                  ) : (
                    <ul className="focus-list">{data!.focus_topics.map((item) => <li key={item.id}><span>{item.name}</span><span className="count-tag">{item.count}</span></li>)}</ul>
                  )}
                </div>
              </div>
            </section>
          </div>

          <footer className="dashboard-footnote"><span>All monitoring and intelligence figures on this page are live workspace data</span><span><StatusLabel state={connection} /></span></footer>
        </>
      )}
    </div>
  );
}

function Metric({ label, value, change, icon, tone }: { label: string; value: string; change: string; icon: React.ReactNode; tone: string }) {
  return <article className="metric-card"><div className={`metric-icon metric-${tone}`}>{icon}</div><span className="metric-label">{label}</span><div className="metric-bottom"><strong>{value}</strong><span className="metric-change">{change}</span></div></article>;
}

function StatusLabel({ state }: { state: "checking" | "connected" | "unavailable" }) {
  const Icon = state === "connected" ? ArrowUpRight : ArrowDownRight;
  return <span className="footer-status"><Icon size={13} />{state === "connected" ? "API connected" : state === "checking" ? "Checking API" : "API offline"}</span>;
}
