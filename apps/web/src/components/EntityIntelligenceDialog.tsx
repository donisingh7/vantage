"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ExternalLink, MessageSquareText, X } from "lucide-react";
import {
  ApiError, documentsApi, intelligenceApi, sourcesApi, watchlistsApi,
  type Company, type Document, type IntelligenceSignal, type Source, type Topic, type Watchlist,
} from "@/lib/api";
import { LoadingStatus, SkeletonLine } from "@/components/loading/Skeleton";

const SIGNAL_TYPE_LABELS: Record<string, string> = {
  product: "Product", competitor: "Competitor", funding: "Funding", partnership: "Partnership",
  acquisition: "Acquisition", leadership: "Leadership", regulation: "Regulation",
  technology: "Technology", market: "Market", pricing: "Pricing", risk: "Risk", other: "Other",
};

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

type EntityKind = "company" | "topic";

export function EntityIntelligenceDialog({
  kind, entity, onClose,
}: {
  kind: EntityKind; entity: Company | Topic; onClose: () => void;
}) {
  const [signals, setSignals] = useState<IntelligenceSignal[]>([]);
  const [watchlists, setWatchlists] = useState<Watchlist[]>([]);
  const [sourcesById, setSourcesById] = useState<Record<string, Source>>({});
  const [documentsById, setDocumentsById] = useState<Record<string, Document>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    const filterParam = kind === "company" ? { company_id: entity.id } : { topic_id: entity.id };

    Promise.all([
      intelligenceApi.listSignals(filterParam), watchlistsApi.listContaining(filterParam), sourcesApi.list(), documentsApi.list(),
    ])
      .then(([signalResult, watchlistResult, sourceList, documentList]) => {
        if (!active) return;
        setSignals(signalResult.items);
        setWatchlists(watchlistResult.items);
        setSourcesById(Object.fromEntries(sourceList.items.map((source) => [source.id, source])));
        setDocumentsById(Object.fromEntries(documentList.items.map((document) => [document.id, document])));
        setError("");
      })
      .catch((cause) => active && setError(cause instanceof ApiError ? cause.message : "Could not load intelligence."))
      .finally(() => active && setLoading(false));

    return () => { active = false; };
  }, [kind, entity.id]);

  const byPriority = [...signals].sort((a, b) => b.importance_score - a.importance_score);
  const byRecency = [...signals].sort((a, b) => b.analyzed_at.localeCompare(a.analyzed_at));
  const typeCounts = new Map<string, number>();
  for (const signal of signals) {
    const key = signal.signal_type ?? "other";
    typeCounts.set(key, (typeCounts.get(key) ?? 0) + 1);
  }
  const typeBreakdown = [...typeCounts.entries()].sort((a, b) => b[1] - a[1]);
  const maxTypeCount = Math.max(1, ...typeBreakdown.map(([, count]) => count));
  const highPriorityCount = signals.filter((signal) => signal.importance_score >= 0.6).length;

  const askQuestion = `What is the latest intelligence about ${entity.name}?`;

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="form-dialog entity-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="entity-detail-title">
        <header>
          <div>
            <span className="section-kicker">{kind === "company" ? "COMPANY" : "TOPIC"}</span>
            <h2 id="entity-detail-title">{entity.name}</h2>
            {kind === "company" && (entity as Company).domain && <p className="section-subtitle">{(entity as Company).domain}</p>}
          </div>
          <button className="icon-action" aria-label="Close dialog" onClick={onClose}><X size={18} /></button>
        </header>

        {entity.description && <p className="document-excerpt">{entity.description}</p>}

        <div className="signal-detail-grid">
          <div><span className="section-kicker">SIGNALS</span><strong>{signals.length}</strong></div>
          <div><span className="section-kicker">HIGH PRIORITY</span><strong>{highPriorityCount}</strong></div>
          <div><span className="section-kicker">WATCHLISTS</span><strong>{watchlists.length}</strong></div>
          <div><span className="section-kicker">LATEST</span><strong>{byRecency[0] ? formatDate(byRecency[0].analyzed_at) : "—"}</strong></div>
        </div>

        {error && <div className="feedback feedback-error" role="alert">{error}</div>}

        {loading ? (
          <>
            <LoadingStatus label="Loading intelligence" />
            <div aria-hidden="true">
              <h3>Priority developments</h3>
              <div className="signal-mini-list">
                {Array.from({ length: 3 }).map((_, index) => (
                  <div className="signal-mini-row" key={index}>
                    <SkeletonLine width={70} height={16} />
                    <div className="signal-mini-copy">
                      <SkeletonLine width="70%" height={12} />
                      <div style={{ marginTop: 4 }}><SkeletonLine width="90%" height={10} /></div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : (
          <>
            {watchlists.length > 0 && (
              <>
                <h3>In watchlists</h3>
                <div className="entity-chips">{watchlists.map((watchlist) => <span className="entity-chip" key={watchlist.id}>{watchlist.name}</span>)}</div>
              </>
            )}

            {typeBreakdown.length > 0 && (
              <>
                <h3>Signal breakdown</h3>
                <div className="distribution-list">
                  {typeBreakdown.map(([type, count]) => (
                    <div className="distribution-row" key={type}>
                      <span className="distribution-label">{SIGNAL_TYPE_LABELS[type] ?? type}</span>
                      <div className="distribution-track"><div className="distribution-fill" style={{ width: `${(count / maxTypeCount) * 100}%` }} /></div>
                      <span className="distribution-count">{count}</span>
                    </div>
                  ))}
                </div>
              </>
            )}

            <h3>Priority developments</h3>
            {byPriority.length === 0 ? (
              <p className="panel-footnote">No intelligence signals linked to {entity.name} yet.</p>
            ) : (
              <div className="signal-mini-list">
                {byPriority.slice(0, 3).map((signal) => (
                  <SignalMiniRow key={signal.id} signal={signal} document={documentsById[signal.document_id]} sourcesById={sourcesById} />
                ))}
              </div>
            )}

            {byRecency.length > 0 && (
              <>
                <h3>History</h3>
                <div className="signal-mini-list">
                  {byRecency.map((signal) => (
                    <SignalMiniRow key={signal.id} signal={signal} document={documentsById[signal.document_id]} sourcesById={sourcesById} />
                  ))}
                </div>
              </>
            )}
          </>
        )}

        <footer className="signal-detail-footer">
          <Link className="primary-button" href={`/workspace/ask?q=${encodeURIComponent(askQuestion)}`}>
            <MessageSquareText size={16} /> Ask about this {kind}
          </Link>
        </footer>
      </section>
    </div>
  );
}

function SignalMiniRow({ signal, document, sourcesById }: { signal: IntelligenceSignal; document?: Document; sourcesById: Record<string, Source> }) {
  const source = document ? sourcesById[document.source_id] : undefined;
  return (
    <div className="signal-mini-row">
      <span className={`sentiment-tag sentiment-${signal.sentiment ?? "neutral"}`}>{SIGNAL_TYPE_LABELS[signal.signal_type ?? "other"]}</span>
      <div className="signal-mini-copy">
        <strong>{signal.title}</strong>
        <span>{source?.name ?? "Unknown source"} · {formatDate(signal.analyzed_at)} · {Math.round(signal.importance_score * 100)}% importance</span>
      </div>
      {document && (
        <a className="icon-action" href={document.canonical_url} target="_blank" rel="noopener noreferrer" aria-label="Open original source">
          <ExternalLink size={14} />
        </a>
      )}
    </div>
  );
}
