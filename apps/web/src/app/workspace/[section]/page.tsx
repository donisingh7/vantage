import { notFound } from "next/navigation";
import { Construction } from "lucide-react";
import { DashboardOverview } from "@/components/DashboardOverview";
import { ResourceManager, type ResourceKind } from "@/components/ResourceManager";
import { WatchlistManager } from "@/components/WatchlistManager";
import { SettingsPanel } from "@/components/SettingsPanel";
import { IntelligenceView } from "@/components/IntelligenceView";
import { AskVantage } from "@/components/AskVantage";

const placeholders: Record<string, { title: string; eyebrow: string; description: string }> = {};

const resourceSections: Record<string, ResourceKind> = {
  companies: "companies",
  topics: "topics",
  sources: "sources",
};

export default async function WorkspaceSectionPage({ params }: { params: Promise<{ section: string }> }) {
  const { section } = await params;

  if (section === "overview") {
    return <DashboardOverview />;
  }

  if (section === "intelligence") {
    return <IntelligenceView />;
  }

  if (section === "ask") {
    return <AskVantage />;
  }

  if (section === "watchlists") {
    return <WatchlistManager />;
  }

  if (section in resourceSections) {
    return <ResourceManager kind={resourceSections[section]} />;
  }

  if (section === "settings") {
    return <SettingsPanel />;
  }

  const content = placeholders[section];
  if (!content) notFound();

  return (
    <div className="placeholder-page">
      <div className="eyebrow"><span className="eyebrow-rule" />{content.eyebrow}</div>
      <h1>{content.title}</h1>
      <p className="heading-subtitle">{content.description}</p>
      <section className="placeholder-surface">
        <div className="placeholder-symbol"><Construction size={19} strokeWidth={1.7} /></div>
        <span className="section-kicker">FOUNDATION PHASE</span>
        <h2>This workspace is taking shape.</h2>
        <p>Data management and intelligence workflows will be introduced in a later Vantage phase.</p>
        <div className="planned-row"><span>Current status</span><strong>Not connected</strong></div>
      </section>
    </div>
  );
}
