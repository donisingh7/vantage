"use client";

import { Suspense, useEffect, useRef, useState, type FormEvent } from "react";
import { useSearchParams } from "next/navigation";
import { ExternalLink, Search, Sparkles } from "lucide-react";
import { ApiError, askApi, type AskResponse } from "@/lib/api";
import { WorkspacePageSkeleton } from "@/components/loading/WorkspacePageSkeleton";

const ASK_STAGES = ["Retrieving evidence", "Reading relevant sources", "Generating grounded answer"];

const EXAMPLE_QUESTIONS = [
  "What recent funding announcements have been collected?",
  "What leadership changes have been reported?",
  "Summarize the most important recent signal.",
];

export function AskVantage() {
  return (
    <Suspense fallback={<WorkspacePageSkeleton />}>
      <AskVantageContent />
    </Suspense>
  );
}

function AskVantageContent() {
  const searchParams = useSearchParams();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<AskResponse | null>(null);
  const [asked, setAsked] = useState(false);
  const prefilled = useRef(false);

  async function ask(value: string) {
    if (!value.trim()) return;
    setLoading(true); setError(""); setAsked(true);
    try {
      setResult(await askApi.ask(value.trim()));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not reach Ask Vantage.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await ask(question);
  }

  useEffect(() => {
    if (prefilled.current) return;
    prefilled.current = true;
    const prefill = searchParams.get("q");
    if (prefill) {
      setQuestion(prefill);
      void ask(prefill);
    }
  }, [searchParams]);

  return (
    <section className="management-page ask-page">
      <header className="management-heading">
        <div>
          <div className="eyebrow"><span className="eyebrow-rule" />RESEARCH ASSISTANT</div>
          <h1>Ask Vantage</h1>
          <p>Ask a question and get an answer grounded only in your indexed, collected documents.</p>
        </div>
      </header>

      <form className="ask-form" onSubmit={(event) => void submit(event)}>
        <label className="ask-input">
          <Search size={16} />
          <input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask about your collected intelligence..."
            maxLength={2000}
          />
        </label>
        <button className="primary-button" type="submit" disabled={loading || !question.trim()} aria-busy={loading}>
          <Sparkles size={16} className={loading ? "spin-icon" : ""} /> {loading ? "Thinking..." : "Ask"}
        </button>
      </form>

      {!asked && (
        <div className="ask-examples">
          <span className="section-kicker">TRY ASKING</span>
          <div className="ask-example-list">
            {EXAMPLE_QUESTIONS.map((example) => (
              <button className="secondary-button compact-button" key={example} onClick={() => setQuestion(example)} type="button">
                {example}
              </button>
            ))}
          </div>
        </div>
      )}

      {error && <div className="feedback feedback-error" role="alert">{error}</div>}

      {loading && (
        <div className="ask-waiting" role="status" aria-label="Working on your answer: retrieving evidence, reading relevant sources, and generating a grounded response">
          <ul className="ask-stage-list" aria-hidden="true">
            {ASK_STAGES.map((stage, index) => (
              <li className="ask-stage" style={{ animationDelay: `${index * 550}ms` }} key={stage}>{stage}</li>
            ))}
          </ul>
        </div>
      )}

      {!loading && result && (
        <div className="ask-answer content-fade-in">
          <div className="ask-answer-heading">
            <span className="section-kicker">
              {result.grounded ? `GROUNDED IN ${result.retrieved_count} RESULT${result.retrieved_count === 1 ? "" : "S"}` : "NO EVIDENCE FOUND"}
            </span>
            {result.provider === "mock" && <span className="mock-badge">Mock AI — no real model was called</span>}
          </div>
          <p className="ask-answer-text">{result.answer}</p>

          {result.citations.length > 0 && (
            <div className="citation-grid">
              {result.citations.map((citation, index) => (
                <a
                  className="citation-card"
                  key={`${citation.document_id}-${index}`}
                  href={citation.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <div className="citation-card-heading">
                    <span className="count-tag">Source {index + 1}</span>
                    <span className="ingestion-last-run">{Math.round(citation.similarity * 100)}% match</span>
                  </div>
                  <h3>{citation.title || "Untitled document"}</h3>
                  <p>{citation.excerpt}</p>
                  <span className="external-source">{citation.source_name} <ExternalLink size={12} /></span>
                </a>
              ))}
            </div>
          )}
        </div>
      )}

      {!loading && asked && result && !result.grounded && (
        <p className="section-subtitle">
          Collect and index documents from the Sources and Intelligence pages, then ask again.
        </p>
      )}
    </section>
  );
}
