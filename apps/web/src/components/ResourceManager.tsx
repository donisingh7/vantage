"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Activity, ExternalLink, Pencil, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import {
  ApiError, companiesApi, ingestionApi, sourcesApi, topicsApi,
  type Company, type CrawlJob, type IngestionInterval, type Source, type SourceManagement, type SourceType, type Topic,
} from "@/lib/api";
import { EntityIntelligenceDialog } from "@/components/EntityIntelligenceDialog";
import { TableSkeleton } from "@/components/loading/TableSkeleton";

const RESOURCE_TABLE_COLUMNS: Record<ResourceKind, number> = { companies: 5, topics: 4, sources: 8 };

export type ResourceKind = "companies" | "topics" | "sources";
type RecordItem = Company | Topic | SourceManagement;
type Values = { name: string; domain: string; description: string; url: string; source_type: SourceType; ingestion_interval: IngestionInterval };
const initialValues = (): Values => ({ name: "", domain: "", description: "", url: "", source_type: "website", ingestion_interval: "manual" });
const labels = { companies: "Company", topics: "Topic", sources: "Source" } as const;
const INGESTION_INTERVAL_LABELS: Record<IngestionInterval, string> = {
  manual: "Manual only",
  every_6_hours: "Every 6 hours",
  every_12_hours: "Every 12 hours",
  every_24_hours: "Every 24 hours",
};
const INGESTION_INTERVAL_MINUTES: Record<IngestionInterval, number | null> = {
  manual: null,
  every_6_hours: 360,
  every_12_hours: 720,
  every_24_hours: 1440,
};

function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function computeNextRun(job: CrawlJob | null | undefined, interval: IngestionInterval): string | null {
  const minutes = INGESTION_INTERVAL_MINUTES[interval];
  const reference = job?.completed_at ?? job?.started_at;
  if (!minutes || !reference) return null;
  return new Date(new Date(reference).getTime() + minutes * 60_000).toISOString();
}

// -- DEPLOYMENT-TRANSITION COMPATIBILITY (temporary) --------------------------------
// Only used when GET /sources/management/view genuinely 404s (old Lambda, new frontend).
// (Two path segments deliberately -- a single-segment /sources/management would collide
// with the pre-Pass-3 GET /sources/{source_id} route and 422 instead of 404 on an old Lambda.)
// Reconstructs the same shape from the two legacy calls it replaces. Since the old
// backend never exposed whether the scheduler is actually enabled, this defaults to
// false (matching current production config) rather than overclaiming automation.
// Remove once the new endpoint is confirmed live in production.
async function loadLegacySources(search: string): Promise<{ items: SourceManagement[]; schedulerEnabled: boolean }> {
  const [sourcesResult, jobsResult] = await Promise.all([sourcesApi.list(search), ingestionApi.listJobs()]);
  const latestBySource: Record<string, CrawlJob> = {};
  for (const job of jobsResult.items) {
    if (!latestBySource[job.source_id] || job.created_at.localeCompare(latestBySource[job.source_id].created_at) > 0) {
      latestBySource[job.source_id] = job;
    }
  }
  return {
    items: sourcesResult.items.map((source) => ({ ...source, latest_job: latestBySource[source.id] ?? null })),
    schedulerEnabled: false,
  };
}
// -- End deployment-transition compatibility ----------------------------------------

async function load(kind: ResourceKind, search: string): Promise<{ items: RecordItem[]; schedulerEnabled: boolean }> {
  if (kind === "companies") return { items: (await companiesApi.list(search)).items, schedulerEnabled: false };
  if (kind === "topics") return { items: (await topicsApi.list(search)).items, schedulerEnabled: false };
  try {
    const result = await sourcesApi.management(search);
    return { items: result.items, schedulerEnabled: result.scheduler_enabled };
  } catch (cause) {
    if (cause instanceof ApiError && cause.status === 404) return await loadLegacySources(search);
    throw cause;
  }
}

function valuesOf(item: RecordItem): Values {
  const record = item as Company & Topic & Source;
  return {
    name: record.name, domain: record.domain ?? "", description: record.description ?? "",
    url: record.url ?? "", source_type: record.source_type ?? "website",
    ingestion_interval: record.ingestion_interval ?? "manual",
  };
}

async function save(kind: ResourceKind, id: string | null, values: Values) {
  if (kind === "companies") {
    const payload = { name: values.name, domain: values.domain || null, description: values.description || null };
    if (id) return companiesApi.update(id, payload);
    return companiesApi.create(payload);
  }
  if (kind === "topics") {
    const payload = { name: values.name, description: values.description || null };
    if (id) return topicsApi.update(id, payload);
    return topicsApi.create(payload);
  }
  const payload = { name: values.name, url: values.url, source_type: values.source_type, ingestion_interval: values.ingestion_interval };
  if (id) return sourcesApi.update(id, payload);
  return sourcesApi.create(payload);
}

export function ResourceManager({ kind }: { kind: ResourceKind }) {
  const [items, setItems] = useState<RecordItem[]>([]);
  const [schedulerEnabled, setSchedulerEnabled] = useState(false);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<RecordItem | null | undefined>(undefined);
  const [values, setValues] = useState<Values>(initialValues);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<RecordItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [ingesting, setIngesting] = useState<string | null>(null);
  const [viewingEntity, setViewingEntity] = useState<Company | Topic | null>(null);
  // True only while a background search reconciliation (see reconcileWithSearch) is in
  // flight -- distinct from `loading`, which is the initial/full-page skeleton state.
  const [reconciling, setReconciling] = useState(false);

  async function refresh(query = search) {
    setLoading(true);
    try {
      const result = await load(kind, query);
      setItems(result.items);
      setSchedulerEnabled(result.schedulerEnabled);
      setError("");
    }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not load records."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(""); }, [kind]);

  // A create/edit can change whether a record belongs in the CURRENT filtered (searched)
  // result set -- e.g. editing "Acme" to "Beta" while searching "Acme" should make it
  // disappear, and creating "Beta" while searching "Acme" should never show it. Rather than
  // duplicate the backend's per-kind search fields (name+domain for companies, name only
  // for topics, name+url for sources) in the frontend, this re-reads the current resource
  // endpoint with the current search term -- one targeted request, no full-page skeleton,
  // existing table stays visible via the `reconciling` busy state instead.
  async function reconcileWithSearch() {
    setReconciling(true);
    try {
      const result = await load(kind, search);
      setItems(result.items);
      setSchedulerEnabled(result.schedulerEnabled);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not refresh search results."); }
    finally { setReconciling(false); }
  }

  async function runIngestion(source: SourceManagement) {
    setIngesting(source.id); setError("");
    try {
      const job = await ingestionApi.run(source.id);
      setItems((prev) => prev.map((item) => (item.id === source.id ? { ...(item as SourceManagement), latest_job: job } : item)));
      setNotice(
        job.status === "completed"
          ? `Ingestion completed for ${source.name}: ${job.documents_created} new of ${job.documents_found} found.`
          : job.status === "failed"
            ? `Ingestion failed for ${source.name}: ${job.error_message ?? "Unknown error"}`
            : `Ingestion is ${job.status} for ${source.name}.`,
      );
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not run ingestion."); }
    finally { setIngesting(null); }
  }

  function openForm(item?: RecordItem) { setEditing(item ?? null); setValues(item ? valuesOf(item) : initialValues()); setError(""); }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError("");
    try {
      const wasEditing = editing && editing !== null ? editing : null;
      const result = await save(kind, wasEditing ? wasEditing.id : null, values);
      setEditing(undefined); setNotice(`${labels[kind]} ${wasEditing ? "updated" : "created"}.`);

      if (search.trim()) {
        // Create/edit can change whether this record still belongs in the active search
        // results -- reconcile against the real backend search instead of guessing locally.
        await reconcileWithSearch();
      } else if (wasEditing) {
        // The update response has no enriched watchlist_count (it's not a DB column), so
        // keep the value already known locally instead of silently zeroing it; same for a
        // source's latest_job, which editing name/url/etc never changes.
        setItems((prev) => prev.map((item) => (item.id === wasEditing.id
          ? { ...item, ...result, watchlist_count: item.watchlist_count, ...("latest_job" in item ? { latest_job: (item as SourceManagement).latest_job } : {}) }
          : item)));
      } else {
        const created = kind === "sources" ? { ...(result as Source), latest_job: null } : result;
        setItems((prev) => [...prev, created as RecordItem].sort((a, b) => a.name.localeCompare(b.name)));
      }
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not save this record."); }
    finally { setSaving(false); }
  }

  async function remove() {
    if (!deleting) return;
    setBusy(true); setError("");
    try {
      if (kind === "companies") await companiesApi.delete(deleting.id);
      else if (kind === "topics") await topicsApi.delete(deleting.id);
      else await sourcesApi.delete(deleting.id);
      setItems((prev) => prev.filter((item) => item.id !== deleting.id));
      setDeleting(null); setNotice(`${labels[kind]} deleted.`);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not delete this record."); }
    finally { setBusy(false); }
  }

  async function toggleSource(source: SourceManagement) {
    setBusy(true);
    try {
      const updated = await sourcesApi.update(source.id, { is_active: !source.is_active });
      setItems((prev) => prev.map((item) => (item.id === source.id
        ? { ...item, ...updated, watchlist_count: item.watchlist_count, latest_job: (item as SourceManagement).latest_job }
        : item)));
      setNotice(`Source ${source.is_active ? "paused" : "activated"}.`);
    }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not update source."); }
    finally { setBusy(false); }
  }

  const fields = kind === "companies"
    ? [{ key: "name", label: "Company name", required: true }, { key: "domain", label: "Domain" }, { key: "description", label: "Description", multiline: true }]
    : kind === "topics"
      ? [{ key: "name", label: "Topic name", required: true }, { key: "description", label: "Description", multiline: true }]
      : [{ key: "name", label: "Source name", required: true }, { key: "url", label: "Public URL", required: true }, { key: "source_type", label: "Source type", required: true }, { key: "ingestion_interval", label: "Ingestion schedule", required: true }];

  return <section className="management-page">
    <header className="management-heading"><div><div className="eyebrow"><span className="eyebrow-rule" />WORKSPACE MANAGEMENT</div><h1>{kind[0].toUpperCase() + kind.slice(1)}</h1><p>{kind === "companies" ? "Organizations in your market map." : kind === "topics" ? "Themes shaping your strategic landscape." : "Public sources for monitoring. Run ingestion to fetch and store their latest content."}</p></div><button className="primary-button" onClick={() => openForm()}><Plus size={16} /> Add {labels[kind].toLowerCase()}</button></header>
    <div className="management-toolbar"><label className="management-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void refresh(); }} placeholder={`Search ${kind}...`} /></label><span className="record-total" aria-live="polite">{reconciling ? <RefreshCw size={12} className="spin-icon" /> : null}{items.length} {items.length === 1 ? "record" : "records"}</span></div>
    {notice && <div className="feedback feedback-success" role="status">{notice}<button aria-label="Dismiss message" onClick={() => setNotice("")}><X size={14} /></button></div>}
    {error && editing === undefined && !deleting && <div className="feedback feedback-error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}><X size={14} /></button></div>}
    {loading ? <TableSkeleton columns={RESOURCE_TABLE_COLUMNS[kind]} label={`Loading ${kind}`} /> : items.length === 0 ? <div className="empty-surface"><div className="empty-symbol"><Plus size={19} /></div><h2>{search ? "No matches found" : "A clear space to start"}</h2><p>{search ? "Try another search." : `No ${kind} yet. Add one to get started.`}</p>{!search && <button className="secondary-button" onClick={() => openForm()}>Add first {labels[kind].toLowerCase()}</button>}</div> : <div className="table-wrap content-fade-in" aria-busy={reconciling}><table className="resource-table"><thead><tr>{(kind === "companies" ? ["Company", "Domain", "Description", "Watchlists"] : kind === "topics" ? ["Topic", "Description", "Watchlists"] : ["Source", "Type", "URL", "Watchlists", "Status", "Last ingestion", "Schedule"]).map((column) => <th key={column}>{column}</th>)}<th><span className="visually-hidden">Actions</span></th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.name}</strong></td>
      {kind === "companies" && <><td className="muted-cell">{(item as Company).domain || "—"}</td><td className="description-cell">{(item as Company).description || "—"}</td><td><span className="count-tag">{item.watchlist_count}</span></td></>}
      {kind === "topics" && <><td className="description-cell">{(item as Topic).description || "—"}</td><td><span className="count-tag">{item.watchlist_count}</span></td></>}
      {kind === "sources" && <><td><span className="type-tag">{(item as SourceManagement).source_type}</span></td><td><a className="external-source" href={(item as SourceManagement).url} target="_blank" rel="noopener noreferrer">{(item as SourceManagement).url}<ExternalLink size={12} /></a></td><td><span className="count-tag">{item.watchlist_count}</span></td><td><button className={`status-toggle ${(item as SourceManagement).is_active ? "status-on" : "status-off"}`} disabled={busy} onClick={() => void toggleSource(item as SourceManagement)}><span />{(item as SourceManagement).is_active ? "Active" : "Paused"}</button></td><td><IngestionStatus job={(item as SourceManagement).latest_job} /></td><td><ScheduleCell source={item as SourceManagement} job={(item as SourceManagement).latest_job} schedulerEnabled={schedulerEnabled} /></td></>}
      <td><div className="row-actions">{(kind === "companies" || kind === "topics") && <button className="icon-action" aria-label={`View intelligence for ${item.name}`} title="View intelligence" onClick={() => setViewingEntity(item as Company | Topic)}><Activity size={15} /></button>}{kind === "sources" && <button className="icon-action" aria-label={`Run ingestion for ${item.name}`} title="Run ingestion" disabled={ingesting === item.id} aria-busy={ingesting === item.id} onClick={() => void runIngestion(item as SourceManagement)}><RefreshCw size={15} className={ingesting === item.id ? "spin-icon" : ""} /></button>}<button className="icon-action" aria-label={`Edit ${item.name}`} title="Edit" onClick={() => openForm(item)}><Pencil size={15} /></button><button className="icon-action action-danger" aria-label={`Delete ${item.name}`} title="Delete" onClick={() => setDeleting(item)}><Trash2 size={15} /></button></div></td></tr>)}</tbody></table></div>}
    {editing !== undefined && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setEditing(undefined); }}><section className="form-dialog" role="dialog" aria-modal="true" aria-labelledby="record-dialog-title"><header><div><span className="section-kicker">{editing ? "EDIT RECORD" : "NEW RECORD"}</span><h2 id="record-dialog-title">{editing ? `Edit ${editing.name}` : `Add ${labels[kind].toLowerCase()}`}</h2></div><button className="icon-action" aria-label="Close dialog" disabled={saving} onClick={() => setEditing(undefined)}><X size={18} /></button></header><form onSubmit={(event) => void submit(event)}>{fields.map((field) => <label className="form-field" key={field.key}><span>{field.label}{field.required && <i> *</i>}</span>{field.key === "source_type" ? <select value={values.source_type} onChange={(event) => setValues({ ...values, source_type: event.target.value as SourceType })}><option value="website">Website</option><option value="rss">RSS</option><option value="news">News</option><option value="blog">Blog</option><option value="other">Other</option></select> : field.key === "ingestion_interval" ? <select value={values.ingestion_interval} onChange={(event) => setValues({ ...values, ingestion_interval: event.target.value as IngestionInterval })}>{(Object.keys(INGESTION_INTERVAL_LABELS) as IngestionInterval[]).map((interval) => <option value={interval} key={interval}>{INGESTION_INTERVAL_LABELS[interval]}</option>)}</select> : field.multiline ? <textarea rows={4} value={values.description} onChange={(event) => setValues({ ...values, description: event.target.value })} /> : <input required={field.required} type={field.key === "url" ? "url" : "text"} value={values[field.key as keyof Values] as string} onChange={(event) => setValues({ ...values, [field.key]: event.target.value })} placeholder={field.key === "url" ? "https://example.com/news" : field.key === "domain" ? "example.com" : ""} />}</label>)}{error && <p className="dialog-error" role="alert">{error}</p>}<footer><button className="secondary-button" type="button" disabled={saving} onClick={() => setEditing(undefined)}>Cancel</button><button className="primary-button" type="submit" disabled={saving} aria-busy={saving}>{saving ? <RefreshCw size={14} className="spin-icon" /> : null}{saving ? "Saving..." : editing ? "Save changes" : "Create"}</button></footer></form></section></div>}
    {deleting && <div className="dialog-backdrop"><section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-title"><span className="section-kicker">DELETE RECORD</span><h2 id="delete-title">Delete {deleting.name}?</h2><p>This record will be removed from this workspace and its watchlist memberships will be cleared.</p>{error && <p className="dialog-error" role="alert">{error}</p>}<footer><button className="secondary-button" disabled={busy} onClick={() => setDeleting(null)}>Cancel</button><button className="danger-button" disabled={busy} aria-busy={busy} onClick={() => void remove()}>{busy ? <RefreshCw size={14} className="spin-icon" /> : null}{busy ? "Deleting..." : "Delete"}</button></footer></section></div>}
    {viewingEntity && (kind === "companies" || kind === "topics") && (
      <EntityIntelligenceDialog kind={kind === "companies" ? "company" : "topic"} entity={viewingEntity} onClose={() => setViewingEntity(null)} />
    )}
  </section>;
}

function IngestionStatus({ job }: { job?: CrawlJob | null }) {
  if (!job) return <span className="ingestion-status ingestion-none">Not run yet</span>;
  const lastRun = formatDateTime(job.completed_at ?? job.started_at);
  if (job.status === "completed") {
    return <span className="ingestion-status-stack"><span className="ingestion-status ingestion-completed">{job.documents_created} new · {job.documents_found} found</span><small className="ingestion-last-run">Last run {lastRun}</small></span>;
  }
  if (job.status === "failed") {
    return <span className="ingestion-status-stack"><span className="ingestion-status ingestion-failed" title={job.error_message ?? undefined}>Failed</span><small className="ingestion-last-run">Last run {lastRun}</small></span>;
  }
  return <span className="ingestion-status ingestion-running">{job.status[0].toUpperCase() + job.status.slice(1)}</span>;
}

function ScheduleCell({ source, job, schedulerEnabled }: { source: Source; job?: CrawlJob | null; schedulerEnabled: boolean }) {
  const nextRun = schedulerEnabled ? computeNextRun(job, source.ingestion_interval) : null;
  return (
    <span className="ingestion-status-stack">
      <span>Configured: {INGESTION_INTERVAL_LABELS[source.ingestion_interval]}</span>
      {schedulerEnabled
        ? nextRun && <small className="ingestion-last-run">Next {formatDateTime(nextRun)}</small>
        : <small className="ingestion-last-run">Automation disabled in this live demo</small>}
    </span>
  );
}
