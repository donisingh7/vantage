import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity, ArrowRight, Building2, Command, FileSearch, Globe2, Layers3, MessageSquareText, Sparkles, Tags,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Vantage | Executive Market Intelligence",
  description:
    "Vantage turns monitored public sources into structured intelligence and grounded answers for decision-makers.",
};

const CAPABILITIES = [
  {
    icon: Building2,
    title: "Companies & topics",
    description: "Track the organizations and strategic themes that matter to your market map.",
  },
  {
    icon: Globe2,
    title: "Public sources",
    description: "Point Vantage at the websites, RSS feeds, news, and blogs you choose to monitor.",
  },
  {
    icon: FileSearch,
    title: "Watchlists",
    description: "Group companies, topics, and sources together around a strategic question.",
  },
  {
    icon: Command,
    title: "Source ingestion",
    description: "Run ingestion on demand to collect documents from your active sources.",
  },
  {
    icon: Sparkles,
    title: "Structured AI intelligence",
    description: "Analyzed documents become signals with sentiment, importance, and business impact.",
  },
  {
    icon: Layers3,
    title: "Semantic indexing & search",
    description: "Collected documents are indexed for meaning-based retrieval, not just keyword matching.",
  },
  {
    icon: MessageSquareText,
    title: "Ask Vantage, with citations",
    description: "Ask a question and get an answer grounded only in your indexed evidence, sources cited.",
  },
];

const STEPS = [
  { title: "Add companies and topics", description: "Define the organizations and themes you want Vantage to track." },
  { title: "Add public sources", description: "Point Vantage at the websites, feeds, and news you want to pull from." },
  { title: "Build a watchlist", description: "Group companies, topics, and sources around a strategic question." },
  { title: "Run ingestion", description: "Collect the latest documents from your active sources." },
  { title: "Analyze and index", description: "Turn collected documents into structured signals and searchable evidence." },
  { title: "Review and ask", description: "Review structured signals and ask Vantage questions grounded in indexed evidence." },
];

const WORKFLOW = ["Public sources", "Collection", "AI analysis", "Searchable intelligence", "Executive answers + citations"];

const CAPABILITY_CARDS = [
  { icon: Globe2, title: "Monitor", description: "Organize companies, topics, and public sources around the market questions you care about." },
  { icon: Sparkles, title: "Analyze", description: "Turn collected documents into structured, prioritized signals." },
  { icon: Layers3, title: "Retrieve", description: "Semantically index evidence for fast, meaning-based search." },
  { icon: MessageSquareText, title: "Ask", description: "Get grounded answers with citations back to source evidence." },
];

export default function LandingPage() {
  return (
    <div className="landing-page">
      <header className="landing-nav">
        <Link className="brand" href="/">
          <span className="brand-mark" aria-hidden="true">V</span>
          <span>vantage<span className="brand-period">.</span></span>
        </Link>
        <nav className="landing-nav-links" aria-label="Page sections">
          <a href="#how-it-works">How it works</a>
          <a href="#capabilities">Capabilities</a>
        </nav>
        <Link className="primary-button" href="/workspace/overview">
          Open workspace <ArrowRight size={15} />
        </Link>
      </header>

      <section className="landing-hero">
        <div className="eyebrow"><span className="eyebrow-rule" />EXECUTIVE MARKET INTELLIGENCE</div>
        <h1>Executive market intelligence from the signals that matter.</h1>
        <p>Vantage turns monitored public sources into structured intelligence and grounded answers for decision-makers.</p>
        <div className="landing-hero-actions">
          <Link className="primary-button" href="/workspace/overview">
            Open workspace <ArrowRight size={16} />
          </Link>
          <a className="secondary-button" href="#how-it-works">See how it works</a>
        </div>
      </section>

      <section className="landing-workflow" aria-label="Product workflow">
        <div className="landing-workflow-track">
          {WORKFLOW.map((step, index) => (
            <div className="landing-workflow-step" key={step}>
              <span className="landing-workflow-node">{step}</span>
              {index < WORKFLOW.length - 1 && <ArrowRight className="landing-workflow-arrow" size={16} aria-hidden="true" />}
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section" id="capabilities">
        <div className="eyebrow"><span className="eyebrow-rule" />WHAT VANTAGE DOES</div>
        <h2>A complete intelligence workflow, in one workspace.</h2>
        <div className="landing-capability-grid">
          {CAPABILITIES.map(({ icon: Icon, title, description }) => (
            <article className="landing-capability-card" key={title}>
              <div className="landing-capability-icon"><Icon size={18} strokeWidth={1.8} aria-hidden="true" /></div>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section" id="how-it-works">
        <div className="eyebrow"><span className="eyebrow-rule" />HOW TO USE VANTAGE</div>
        <h2>From public sources to grounded answers, in six steps.</h2>
        <ol className="landing-steps">
          {STEPS.map((step, index) => (
            <li className="landing-step" key={step.title}>
              <span className="landing-step-number">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <h3>{step.title}</h3>
                <p>{step.description}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="landing-section">
        <div className="eyebrow"><span className="eyebrow-rule" />CAPABILITIES</div>
        <h2>Monitor. Analyze. Retrieve. Ask.</h2>
        <div className="landing-card-grid">
          {CAPABILITY_CARDS.map(({ icon: Icon, title, description }) => (
            <article className="landing-mini-card" key={title}>
              <div className="landing-capability-icon"><Icon size={18} strokeWidth={1.8} aria-hidden="true" /></div>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-cta">
        <Activity size={22} strokeWidth={1.6} aria-hidden="true" />
        <h2>See your market, in focus.</h2>
        <p>Open the workspace to explore companies, topics, watchlists, and grounded intelligence.</p>
        <Link className="primary-button" href="/workspace/overview">
          Open the live workspace <ArrowRight size={16} />
        </Link>
      </section>

      <footer className="landing-footer">
        <Tags size={14} aria-hidden="true" />
        <p>
          Vantage is a solo-built portfolio project demonstrating a full monitoring-to-intelligence workflow. This is a
          live, working demo workspace with sample data — not a production deployment for a real company or customer base.
        </p>
      </footer>
    </div>
  );
}
