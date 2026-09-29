"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ExternalLink, Layers, MessageSquareText, Sparkles, X } from "lucide-react";
import {
  ApiError, companiesApi, documentsApi, getSystemInfo, intelligenceApi, searchApi, sourcesApi, topicsApi,
  type Company, type Document, type IntelligenceSignal, type Sentiment, type SignalType, type Source, type Topic,
} from "@/lib/api";
import { CardGridSkeleton, DocumentListSkeleton } from "@/components/loading/CardGridSkeleton";

const SIGNAL_TYPE_LABELS: Record<string, string> = {
  product: "Product", competitor: "Competitor", funding: "Funding", partnership: "Partnership",
  acquisition: "Acquisition", leadership: "Leadership", regulation: "Regulation",
  technology: "Technology", market: "Market", pricing: "Pricing", risk: "Risk", other: "Other",
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

type SortMode = "priority" | "recent";

const SENTIMENT_OPTIONS: Sentiment[] = ["positive", "neutral", "negative", "mixed"];
const SIGNAL_TYPE_OPTIONS: SignalType[] = [
  "product", "competitor", "funding", "partnership", "acquisition", "leadership",
  "regulation", "technology", "market", "pricing", "risk", "other",
];

export function IntelligenceView() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [signals, setSignals] = useState<IntelligenceSignal[]>([]);
  const [sourcesById, setSourcesById] = useState<Record<string, Source>>({});
  const [documentsById, setDocumentsById] = useState<Record<string, Document>>({});
  const [companiesById, setCompaniesById] = useState<Record<string, Company>>({});
  const [topicsById, setTopicsById] = useState<Record<string, Topic>>({});
  const [companies, setCompanies] = useState<Company[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [analyzing, setAnalyzing] = useState<string | null>(null);
  const [analyzingPending, setAnalyzingPending] = useState(false);
  const [indexing, setIndexing] = useState<string | null>(null);
  const [indexingPending, setIndexingPending] = useState(false);
  const [isMock, setIsMock] = useState(true);
  const [detail, setDetail] = useState<IntelligenceSignal | null>(null);

  const [filterCompany, setFilterCompany] = useState("");
  const [filterTopic, setFilterTopic] = useState("");
  const [filterSignalType, setFilterSignalType] = useState("");
  const [filterSentiment, setFilterSentiment] = useState("");
  const [sortMode, setSortMode] = useState<SortMode>("priority");

  async function refresh() {
    setLoading(true);
    try {
      const [documentList, signalList, sourceList, companyList, topicList, systemInfo] = await Promise.all([
        documentsApi.list(),
        intelligenceApi.listSignals({
          company_id: filterCompany || undefined,
          topic_id: filterTopic || undefined,
          signal_type: (filterSignalType || undefined) as SignalType | undefined,
          sentiment: (filterSentiment || undefined) as Sentiment | undefined,
        }),
        sourcesApi.list(), companiesApi.list(), topicsApi.list(), getSystemInfo(),
      ]);
      setDocuments(documentList.items);
      setSignals(signalList.items);
      setSourcesById(Object.fromEntries(sourceList.items.map((source) => [source.id, source])));
      setDocumentsById(Object.fromEntries(documentList.items.map((document) => [document.id, document])));
      setCompanies(companyList.items);
      setTopics(topicList.items);
      setCompaniesById(Object.fromEntries(companyList.items.map((company) => [company.id, company])));
      setTopicsById(Object.fromEntries(topicList.items.map((topic) => [topic.id, topic])));
      setIsMock(systemInfo.llm_provider === "mock");
      setError("");
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not load intelligence data.");
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { void refresh(); }, [filterCompany, filterTopic, filterSignalType, filterSentiment]);

  const sortedSignals = [...signals].sort((a, b) =>
    sortMode === "recent" ? b.analyzed_at.localeCompare(a.analyzed_at) : b.importance_score - a.importance_score,
  );

  async function analyzeDocument(document: Document) {
    setAnalyzing(document.id); setError("");
    try {
      await documentsApi.analyze(document.id, document.analysis_status != null);
      setNotice(`Analysis complete for "${document.title ?? "document"}".`);
      await refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not analyze document.");
    } finally {
      setAnalyzing(null);
    }
  }

  async function analyzePending() {
    setAnalyzingPending(true); setError("");
    try {
      const result = await intelligenceApi.analyzePending(5);
      setNotice(`Analyzed ${result.analyzed} pending document${result.analyzed === 1 ? "" : "s"}.`);
      await refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not analyze pending documents.");
    } finally {
      setAnalyzingPending(false);
    }
  }

  async function indexDocument(document: Document) {
    setIndexing(document.id); setError("");
    try {
      const result = await documentsApi.index(document.id, document.indexed);
      setNotice(
        result.skipped
          ? `"${document.title ?? "Document"}" is already indexed (${result.total_chunks} chunks).`
          : `Indexed "${document.title ?? "document"}" into ${result.chunks_created} chunks.`,
      );
      await refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not index document.");
    } finally {
      setIndexing(null);
    }
  }

  async function indexPending() {
    setIndexingPending(true); setError("");
    try {
      const result = await searchApi.indexPending(5);
      setNotice(`Indexed ${result.indexed} pending document${result.indexed === 1 ? "" : "s"} for search.`);
      await refresh();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not index pending documents.");
    } finally {
      setIndexingPending(false);
    }
  }

  const pendingCount = documents.filter((document) => !document.analysis_status).length;
  const pendingIndexCount = documents.filter((document) => !document.indexed).length;

  return (
    <section className="management-page">
      <header className="management-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-rule" />MARKET INTELLIGENCE</div>
          <h1>Intelligence</h1>
          <p>Documents collected from your sources, and structured signals analyzed from them.</p>
        </div>
        <div className="row-actions">
          <button className="secondary-button" disabled={indexingPending || pendingIndexCount === 0} aria-busy={indexingPending} onClick={() => void indexPending()}>
            <Layers size={16} className={indexingPending ? "spin-icon" : ""} /> {indexingPending ? "Indexing..." : `Index pending (${pendingIndexCount})`}
          </button>
          <button className="primary-button" disabled={analyzingPending || pendingCount === 0} aria-busy={analyzingPending} onClick={() => void analyzePending()}>
            <Sparkles size={16} className={analyzingPending ? "spin-icon" : ""} /> {analyzingPending ? "Analyzing..." : `Analyze pending (${pendingCount})`}
          </button>
        </div>
      </header>

      {notice && <div className="feedback feedback-success" role="status">{notice}<button aria-label="Dismiss message" onClick={() => setNotice("")}><X size={14} /></button></div>}
      {error && <div className="feedback feedback-error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}><X size={14} /></button></div>}

      <section className="intelligence-section">
        <div className="intelligence-section-heading">
          <h2>Analyzed Intelligence</h2>
          {isMock && <span className="mock-badge">Mock AI — no real model was called</span>}
        </div>

        <div className="filter-bar">
          <select value={filterCompany} onChange={(event) => setFilterCompany(event.target.value)} aria-label="Filter by company">
            <option value="">All companies</option>
            {companies.map((company) => <option value={company.id} key={company.id}>{company.name}</option>)}
          </select>
          <select value={filterTopic} onChange={(event) => setFilterTopic(event.target.value)} aria-label="Filter by topic">
            <option value="">All topics</option>
            {topics.map((topic) => <option value={topic.id} key={topic.id}>{topic.name}</option>)}
          </select>
          <select value={filterSignalType} onChange={(event) => setFilterSignalType(event.target.value)} aria-label="Filter by signal type">
            <option value="">All signal types</option>
            {SIGNAL_TYPE_OPTIONS.map((type) => <option value={type} key={type}>{SIGNAL_TYPE_LABELS[type]}</option>)}
          </select>
          <select value={filterSentiment} onChange={(event) => setFilterSentiment(event.target.value)} aria-label="Filter by sentiment">
            <option value="">All sentiment</option>
            {SENTIMENT_OPTIONS.map((sentiment) => <option value={sentiment} key={sentiment}>{sentiment}</option>)}
          </select>
          <div className="sort-toggle">
            <button className={sortMode === "priority" ? "sort-toggle-active" : ""} onClick={() => setSortMode("priority")} type="button">Priority</button>
            <button className={sortMode === "recent" ? "sort-toggle-active" : ""} onClick={() => setSortMode("recent")} type="button">Recent</button>
          </div>
        </div>

        {loading ? (
          <CardGridSkeleton label="Loading analyzed intelligence" />
        ) : sortedSignals.length === 0 ? (
          <div className="empty-surface"><h2>No intelligence yet</h2><p>Analyze a collected document below to generate a structured signal, or clear your filters.</p></div>
        ) : (
          <div className="signal-card-grid content-fade-in">
            {sortedSignals.map((signal) => {
              const document = documentsById[signal.document_id];
              const source = document ? sourcesById[document.source_id] : undefined;
              const company = signal.company_id ? companiesById[signal.company_id] : undefined;
              const topic = signal.topic_id ? topicsById[signal.topic_id] : undefined;
              return (
                <button className="signal-card" key={signal.id} onClick={() => setDetail(signal)}>
                  <div className="signal-card-heading">
                    <span className="type-tag">{SIGNAL_TYPE_LABELS[signal.signal_type ?? "other"]}</span>
                    <span className={`sentiment-tag sentiment-${signal.sentiment ?? "neutral"}`}>{signal.sentiment ?? "neutral"}</span>
                  </div>
                  <h3>{signal.title}</h3>
                  <p>{signal.executive_summary}</p>
                  {(company || topic) && (
                    <div className="entity-chips">
                      {company && <span className="entity-chip">{company.name}</span>}
                      {topic && <span className="entity-chip">{topic.name}</span>}
                    </div>
                  )}
                  <div className="signal-card-meta">
                    <span>{source?.name ?? "Unknown source"}</span>
                    <span>Importance {Math.round(signal.importance_score * 100)}%</span>
                    <span>Relevance {Math.round(signal.relevance_score * 100)}%</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section className="intelligence-section">
        <h2>Collected</h2>
        <p className="section-subtitle">Raw documents fetched from your active sources. This list is not analyzed intelligence by itself.</p>
        {loading ? (
          <DocumentListSkeleton />
        ) : documents.length === 0 ? (
          <div className="empty-surface"><h2>No documents collected yet</h2><p>Run ingestion from a source on the Sources page to collect its content here.</p></div>
        ) : (
          <div className="document-list content-fade-in">
            {documents.map((document) => (
              <article className="document-card" key={document.id}>
                <div className="document-card-heading">
                  <h2>{document.title || "Untitled document"}</h2>
                  <a className="external-source" href={document.canonical_url} target="_blank" rel="noopener noreferrer">
                    Original <ExternalLink size={12} />
                  </a>
                </div>
                <div className="document-meta">
                  <span>{sourcesById[document.source_id]?.name ?? "Unknown source"}</span>
                  <span>Published {formatDate(document.published_at)}</span>
                  <span>Fetched {formatDate(document.fetched_at)}</span>
                </div>
                {document.excerpt && <p className="document-excerpt">{document.excerpt}</p>}
                <div className="document-actions">
                  <div className="row-actions">
                    <DocumentAnalysisStatus status={document.analysis_status} />
                    <span className={`ingestion-status ${document.indexed ? "ingestion-completed" : "ingestion-none"}`}>
                      {document.indexed ? "Indexed" : "Not indexed"}
                    </span>
                  </div>
                  <div className="row-actions">
                    <button
                      className="secondary-button compact-button"
                      disabled={indexing === document.id}
                      aria-busy={indexing === document.id}
                      onClick={() => void indexDocument(document)}
                    >
                      {indexing === document.id && <Layers size={13} className="spin-icon" />}
                      {indexing === document.id ? "Indexing..." : document.indexed ? "Re-index" : "Index"}
                    </button>
                    <button
                      className="secondary-button compact-button"
                      disabled={analyzing === document.id}
                      aria-busy={analyzing === document.id}
                      onClick={() => void analyzeDocument(document)}
                    >
                      {analyzing === document.id && <Sparkles size={13} className="spin-icon" />}
                      {analyzing === document.id ? "Analyzing..." : document.analysis_status ? "Re-analyze" : "Analyze"}
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {detail && (
        <SignalDetailDialog
          signal={detail}
          document={documentsById[detail.document_id]}
          source={documentsById[detail.document_id] ? sourcesById[documentsById[detail.document_id].source_id] : undefined}
          company={detail.company_id ? companiesById[detail.company_id] : undefined}
          topic={detail.topic_id ? topicsById[detail.topic_id] : undefined}
          isMock={isMock}
          onClose={() => setDetail(null)}
        />
      )}
    </section>
  );
}

function DocumentAnalysisStatus({ status }: { status: Document["analysis_status"] }) {
  if (!status) return <span className="ingestion-status ingestion-none">Not analyzed</span>;
  if (status === "completed") return <span className="ingestion-status ingestion-completed">Analyzed</span>;
  if (status === "irrelevant") return <span className="ingestion-status ingestion-none">Irrelevant</span>;
  return <span className="ingestion-status ingestion-failed">Failed</span>;
}

function SignalDetailDialog({
  signal, document, source, company, topic, isMock, onClose,
}: {
  signal: IntelligenceSignal; document?: Document; source?: Source; company?: Company; topic?: Topic;
  isMock: boolean; onClose: () => void;
}) {
  const askQuestion = `Tell me more about "${signal.title ?? "this signal"}" and why it matters.`;
  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="form-dialog signal-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="signal-detail-title">
        <header>
          <div>
            <span className="section-kicker">{SIGNAL_TYPE_LABELS[signal.signal_type ?? "other"]}{isMock ? " · MOCK AI" : ""}</span>
            <h2 id="signal-detail-title">{signal.title}</h2>
            {(company || topic) && (
              <div className="entity-chips">
                {company && <span className="entity-chip">{company.name}</span>}
                {topic && <span className="entity-chip">{topic.name}</span>}
              </div>
            )}
          </div>
          <button className="icon-action" aria-label="Close dialog" onClick={onClose}><X size={18} /></button>
        </header>
        <p className="document-excerpt">{signal.executive_summary}</p>
        <div className="signal-detail-grid">
          <div><span className="section-kicker">IMPORTANCE</span><strong>{Math.round(signal.importance_score * 100)}%</strong></div>
          <div><span className="section-kicker">RELEVANCE</span><strong>{Math.round(signal.relevance_score * 100)}%</strong></div>
          <div><span className="section-kicker">CONFIDENCE</span><strong>{Math.round(signal.confidence_score * 100)}%</strong></div>
          <div><span className="section-kicker">SENTIMENT</span><strong>{signal.sentiment ?? "—"}</strong></div>
        </div>
        {signal.key_points.length > 0 && (
          <>
            <h3>What happened</h3>
            <ul className="signal-points">{signal.key_points.map((point) => <li key={point}>{point}</li>)}</ul>
          </>
        )}
        {signal.business_impact && (<><h3>Why it matters</h3><p>{signal.business_impact}</p></>)}
        {signal.key_entities.length > 0 && (
          <>
            <h3>Key entities</h3>
            <div className="entity-chips">{signal.key_entities.map((entity) => <span className="entity-chip" key={entity}>{entity}</span>)}</div>
          </>
        )}
        {signal.evidence_excerpt && (<><h3>Evidence</h3><blockquote className="evidence-quote">{signal.evidence_excerpt}</blockquote></>)}
        <footer className="signal-detail-footer">
          <span className="ingestion-last-run">Analyzed {formatDateTime(signal.analyzed_at)}</span>
          <div className="row-actions">
            <Link className="secondary-button compact-button" href={`/workspace/ask?q=${encodeURIComponent(askQuestion)}`}>
              <MessageSquareText size={14} /> Ask about this
            </Link>
            {document && (
              <a className="external-source" href={document.canonical_url} target="_blank" rel="noopener noreferrer">
                Original source{source ? ` (${source.name})` : ""} <ExternalLink size={12} />
              </a>
            )}
          </div>
        </footer>
      </section>
    </div>
  );
}
