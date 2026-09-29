"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, ArrowUpRight, ArrowDownRight, Building2, FileSearch, Globe2, Sparkles, Tags } from "lucide-react";
import {
  ApiError, companiesApi, getSystemInfo, ingestionApi, intelligenceApi, sourcesApi, topicsApi, workspaceApi,
  type Company, type CrawlJob, type IntelligenceSignal, type Source, type Topic, type WorkspaceSummary,
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

function countBy<T>(items: T[], key: (item: T) => string): Map<string, number> {
  const counts = new Map<string, number>();
  for (const item of items) {
    const value = key(item);
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return counts;
}

function topFocus(
  signals: IntelligenceSignal[], field: "company_id" | "topic_id", namesById: Record<string, string>, limit = 3,
): { name: string; count: number }[] {
  const counts = countBy(
    signals.filter((signal) => signal[field]),
    (signal) => signal[field] as string,
  );
  return [...counts.entries()]
    .map(([id, count]) => ({ name: namesById[id] ?? "Unknown", count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}

export function DashboardOverview() {
  const [connection, setConnection] = useState<"checking" | "connected" | "unavailable">("checking");
  const [summary, setSummary] = useState<WorkspaceSummary | null>(null);
  const [summaryError, setSummaryError] = useState("");
  const [signals, setSignals] = useState<IntelligenceSignal[] | null>(null);
  const [jobs, setJobs] = useState<CrawlJob[] | null>(null);
  const [sourcesById, setSourcesById] = useState<Record<string, Source>>({});
  const [companiesById, setCompaniesById] = useState<Record<string, string>>({});
  const [topicsById, setTopicsById] = useState<Record<string, string>>({});
  const [isMock, setIsMock] = useState(true);

  useEffect(() => {
    let active = true;
    getSystemInfo()
      .then((info) => {
        if (!active) return;
        setConnection("connected");
        setIsMock(info.llm_provider === "mock");
      })
      .catch(() => {
        if (active) setConnection("unavailable");
      });
    workspaceApi
      .summary()
      .then((value) => active && setSummary(value))
      .catch((cause) => {
        if (active) setSummaryError(cause instanceof ApiError ? cause.message : "Could not load workspace summary.");
      });
    intelligenceApi
      .listSignals()
      .then((result) => active && setSignals(result.items))
      .catch(() => active && setSignals([]));
    ingestionApi
      .listJobs()
      .then((result) => active && setJobs(result.items))
      .catch(() => active && setJobs([]));
    Promise.all([sourcesApi.list(), companiesApi.list(), topicsApi.list()])
      .then(([sources, companies, topics]) => {
        if (!active) return;
        setSourcesById(Object.fromEntries(sources.items.map((source: Source) => [source.id, source])));
        setCompaniesById(Object.fromEntries(companies.items.map((company: Company) => [company.id, company.name])));
        setTopicsById(Object.fromEntries(topics.items.map((topic: Topic) => [topic.id, topic.name])));
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  const prioritySignals = (signals ?? []).slice(0, 3);
  const latestSignals = signals
    ? [...signals].sort((a, b) => b.analyzed_at.localeCompare(a.analyzed_at)).slice(0, 3)
    : [];
  const recentJobs = jobs ? [...jobs].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 5) : [];

  const signalTypeCounts = signals ? [...countBy(signals, (s) => s.signal_type ?? "other").entries()].sort((a, b) => b[1] - a[1]) : [];
  const sentimentCounts = signals ? [...countBy(signals, (s) => s.sentiment ?? "neutral").entries()].sort((a, b) => b[1] - a[1]) : [];
  const maxSignalTypeCount = Math.max(1, ...signalTypeCounts.map(([, count]) => count));
  const maxSentimentCount = Math.max(1, ...sentimentCounts.map(([, count]) => count));
  const focusCompanies = signals ? topFocus(signals, "company_id", companiesById) : [];
  const focusTopics = signals ? topFocus(signals, "topic_id", topicsById) : [];

  return (
    <div className="dashboard-page">
      <section className="page-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-rule" />SATURDAY, SEPTEMBER 26, 2026</div>
          <h1>Good morning, Jordan<span>.</span></h1>
          <p className="heading-subtitle">Your market, in focus.</p>
        </div>
        <div className={`connection-pill connection-${connection}`}>
          <span className="connection-dot" />
          {connection === "connected" ? "API connected" : connection === "checking" ? "Connecting" : "API unavailable"}
        </div>
      </section>

      <section className="metric-grid" aria-label="Workspace monitoring summary">
        <Metric label="Companies monitored" value={formatCount(summary?.companies)} change="In this workspace" icon={<Building2 size={17} />} tone="green" />
        <Metric label="Topics tracked" value={formatCount(summary?.topics)} change="In this workspace" icon={<Tags size={17} />} tone="amber" />
        <Metric label="Active watchlists" value={formatCount(summary?.active_watchlists)} change={summary ? `${summary.watchlists} total` : "Loading"} icon={<FileSearch size={17} />} tone="coral" />
        <Metric label="Active sources" value={formatCount(summary?.active_sources)} change={summary ? `${summary.sources} total` : "Loading"} icon={<Globe2 size={17} />} tone="blue" />
      </section>
      {summaryError && <p className="dialog-error" role="alert">{summaryError}</p>}

      <section className="section-block signal-section">
        <div className="section-heading">
          <div><span className="section-kicker">WHAT MATTERS NOW{isMock ? " · MOCK AI" : ""}</span><h2>Priority signals</h2></div>
          <Link className="text-link" href="/workspace/intelligence">All intelligence <ArrowRight size={15} /></Link>
        </div>
        <div className="signal-list">
          {signals === null ? (
            <SignalListSkeleton />
          ) : prioritySignals.length === 0 ? (
            <p className="panel-footnote">No analyzed intelligence yet. Analyze a collected document on the Intelligence page.</p>
          ) : (
            prioritySignals.map((signal) => (
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
            {signals === null ? (
              <DistributionSkeleton />
            ) : signalTypeCounts.length === 0 ? (
              <p className="panel-footnote">No analyzed intelligence yet.</p>
            ) : (
              <div className="distribution-list">
                {signalTypeCounts.map(([type, count]) => (
                  <div className="distribution-row" key={type}>
                    <span className="distribution-label">{SIGNAL_TYPE_LABELS[type] ?? type}</span>
                    <div className="distribution-track"><div className="distribution-fill" style={{ width: `${(count / maxSignalTypeCount) * 100}%` }} /></div>
                    <span className="distribution-count">{count}</span>
                  </div>
                ))}
              </div>
            )}
            {signals !== null && sentimentCounts.length > 0 && (
              <>
                <p className="distribution-subheading">By sentiment</p>
                <div className="distribution-list">
                  {sentimentCounts.map(([sentiment, count]) => (
                    <div className="distribution-row" key={sentiment}>
                      <span className="distribution-label">{sentiment}</span>
                      <div className="distribution-track"><div className={`distribution-fill sentiment-fill-${sentiment}`} style={{ width: `${(count / maxSentimentCount) * 100}%` }} /></div>
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
            {signals === null ? (
              <TimelineListSkeleton label="Loading latest intelligence" />
            ) : latestSignals.length === 0 ? (
              <p className="panel-footnote">No analyzed intelligence yet.</p>
            ) : (
              latestSignals.map((signal) => (
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
            {jobs === null ? (
              <TimelineListSkeleton label="Loading ingestion activity" />
            ) : recentJobs.length === 0 ? (
              <p className="panel-footnote">No ingestion runs yet. Run ingestion from the Sources page.</p>
            ) : (
              recentJobs.map((job) => (
                <article className="timeline-item" key={job.id}>
                  <span className="timeline-time">{formatShortDate(job.created_at)}</span>
                  <div className="timeline-copy">
                    <span>{sourcesById[job.source_id]?.name ?? "Unknown source"}</span>
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
              {signals === null ? <FocusListSkeleton /> : focusCompanies.length === 0 ? (
                <p className="panel-footnote">No company-linked signals yet.</p>
              ) : (
                <ul className="focus-list">{focusCompanies.map((item) => <li key={item.name}><span>{item.name}</span><span className="count-tag">{item.count}</span></li>)}</ul>
              )}
            </div>
            <div>
              <span className="section-kicker">TOP TOPICS</span>
              {signals === null ? <FocusListSkeleton /> : focusTopics.length === 0 ? (
                <p className="panel-footnote">No topic-linked signals yet.</p>
              ) : (
                <ul className="focus-list">{focusTopics.map((item) => <li key={item.name}><span>{item.name}</span><span className="count-tag">{item.count}</span></li>)}</ul>
              )}
            </div>
          </div>
        </section>
      </div>

      <footer className="dashboard-footnote"><span>All monitoring and intelligence figures on this page are live workspace data</span><span><StatusLabel state={connection} /></span></footer>
    </div>
  );
}

function formatCount(value: number | undefined): string {
  return value === undefined ? "—" : String(value).padStart(2, "0");
}

function Metric({ label, value, change, icon, tone }: { label: string; value: string; change: string; icon: React.ReactNode; tone: string }) {
  return <article className="metric-card"><div className={`metric-icon metric-${tone}`}>{icon}</div><span className="metric-label">{label}</span><div className="metric-bottom"><strong>{value}</strong><span className="metric-change">{change}</span></div></article>;
}

function StatusLabel({ state }: { state: "checking" | "connected" | "unavailable" }) {
  const Icon = state === "connected" ? ArrowUpRight : ArrowDownRight;
  return <span className="footer-status"><Icon size={13} />{state === "connected" ? "API connected" : state === "checking" ? "Checking API" : "API offline"}</span>;
}
