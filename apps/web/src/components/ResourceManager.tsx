"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Activity, ExternalLink, Pencil, Plus, RefreshCw, Search, Trash2, X } from "lucide-react";
import { ApiError, companiesApi, ingestionApi, sourcesApi, topicsApi, type Company, type CrawlJob, type IngestionInterval, type Source, type SourceType, type Topic } from "@/lib/api";
import { EntityIntelligenceDialog } from "@/components/EntityIntelligenceDialog";

export type ResourceKind = "companies" | "topics" | "sources";
type RecordItem = Company | Topic | Source;
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

function computeNextRun(job: CrawlJob | undefined, interval: IngestionInterval): string | null {
  const minutes = INGESTION_INTERVAL_MINUTES[interval];
  const reference = job?.completed_at ?? job?.started_at;
  if (!minutes || !reference) return null;
  return new Date(new Date(reference).getTime() + minutes * 60_000).toISOString();
}

async function load(kind: ResourceKind, search: string): Promise<RecordItem[]> {
  if (kind === "companies") return (await companiesApi.list(search)).items;
  if (kind === "topics") return (await topicsApi.list(search)).items;
  return (await sourcesApi.list(search)).items;
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
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState<RecordItem | null | undefined>(undefined);
  const [values, setValues] = useState<Values>(initialValues);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<RecordItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [jobsBySource, setJobsBySource] = useState<Record<string, CrawlJob>>({});
  const [ingesting, setIngesting] = useState<string | null>(null);
  const [viewingEntity, setViewingEntity] = useState<Company | Topic | null>(null);

  async function refresh(query = search) {
    setLoading(true);
    try {
      setItems(await load(kind, query));
      setError("");
      if (kind === "sources") await refreshJobs();
    }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not load records."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(""); }, [kind]);

  async function refreshJobs() {
    try {
      const jobs = (await ingestionApi.listJobs()).items;
      const latest: Record<string, CrawlJob> = {};
      for (const job of jobs) if (!latest[job.source_id]) latest[job.source_id] = job;
      setJobsBySource(latest);
    } catch { /* last-ingestion status is a convenience; ignore failures here */ }
  }

  async function runIngestion(source: Source) {
    setIngesting(source.id); setError("");
    try {
      const job = await ingestionApi.run(source.id);
      setJobsBySource((prev) => ({ ...prev, [source.id]: job }));
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
      await save(kind, editing && editing !== null ? editing.id : null, values);
      setEditing(undefined); setNotice(`${labels[kind]} ${editing ? "updated" : "created"}.`); await refresh();
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
      setDeleting(null); setNotice(`${labels[kind]} deleted.`); await refresh();
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not delete this record."); }
    finally { setBusy(false); }
  }

  async function toggleSource(source: Source) {
    setBusy(true);
    try { await sourcesApi.update(source.id, { is_active: !source.is_active }); setNotice(`Source ${source.is_active ? "paused" : "activated"}.`); await refresh(); }
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
    <div className="management-toolbar"><label className="management-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") void refresh(); }} placeholder={`Search ${kind}...`} /></label><span className="record-total">{items.length} {items.length === 1 ? "record" : "records"}</span></div>
    {notice && <div className="feedback feedback-success" role="status">{notice}<button aria-label="Dismiss message" onClick={() => setNotice("")}><X size={14} /></button></div>}
    {error && editing === undefined && !deleting && <div className="feedback feedback-error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}><X size={14} /></button></div>}
    {loading ? <div className="loading-surface">Loading {kind}...</div> : items.length === 0 ? <div className="empty-surface"><div className="empty-symbol"><Plus size={19} /></div><h2>{search ? "No matches found" : "A clear space to start"}</h2><p>{search ? "Try another search." : `No ${kind} yet. Add one to get started.`}</p>{!search && <button className="secondary-button" onClick={() => openForm()}>Add first {labels[kind].toLowerCase()}</button>}</div> : <div className="table-wrap"><table className="resource-table"><thead><tr>{(kind === "companies" ? ["Company", "Domain", "Description", "Watchlists"] : kind === "topics" ? ["Topic", "Description", "Watchlists"] : ["Source", "Type", "URL", "Watchlists", "Status", "Last ingestion", "Schedule"]).map((column) => <th key={column}>{column}</th>)}<th><span className="visually-hidden">Actions</span></th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.name}</strong></td>
      {kind === "companies" && <><td className="muted-cell">{(item as Company).domain || "—"}</td><td className="description-cell">{(item as Company).description || "—"}</td><td><span className="count-tag">{item.watchlist_count}</span></td></>}
      {kind === "topics" && <><td className="description-cell">{(item as Topic).description || "—"}</td><td><span className="count-tag">{item.watchlist_count}</span></td></>}
      {kind === "sources" && <><td><span className="type-tag">{(item as Source).source_type}</span></td><td><a className="external-source" href={(item as Source).url} target="_blank" rel="noopener noreferrer">{(item as Source).url}<ExternalLink size={12} /></a></td><td><span className="count-tag">{item.watchlist_count}</span></td><td><button className={`status-toggle ${(item as Source).is_active ? "status-on" : "status-off"}`} disabled={busy} onClick={() => void toggleSource(item as Source)}><span />{(item as Source).is_active ? "Active" : "Paused"}</button></td><td><IngestionStatus job={jobsBySource[item.id]} /></td><td><ScheduleCell source={item as Source} job={jobsBySource[item.id]} /></td></>}
      <td><div className="row-actions">{(kind === "companies" || kind === "topics") && <button className="icon-action" aria-label={`View intelligence for ${item.name}`} title="View intelligence" onClick={() => setViewingEntity(item as Company | Topic)}><Activity size={15} /></button>}{kind === "sources" && <button className="icon-action" aria-label={`Run ingestion for ${item.name}`} title="Run ingestion" disabled={ingesting === item.id} onClick={() => void runIngestion(item as Source)}><RefreshCw size={15} className={ingesting === item.id ? "spin-icon" : ""} /></button>}<button className="icon-action" aria-label={`Edit ${item.name}`} title="Edit" onClick={() => openForm(item)}><Pencil size={15} /></button><button className="icon-action action-danger" aria-label={`Delete ${item.name}`} title="Delete" onClick={() => setDeleting(item)}><Trash2 size={15} /></button></div></td></tr>)}</tbody></table></div>}
    {editing !== undefined && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !saving) setEditing(undefined); }}><section className="form-dialog" role="dialog" aria-modal="true" aria-labelledby="record-dialog-title"><header><div><span className="section-kicker">{editing ? "EDIT RECORD" : "NEW RECORD"}</span><h2 id="record-dialog-title">{editing ? `Edit ${editing.name}` : `Add ${labels[kind].toLowerCase()}`}</h2></div><button className="icon-action" aria-label="Close dialog" disabled={saving} onClick={() => setEditing(undefined)}><X size={18} /></button></header><form onSubmit={(event) => void submit(event)}>{fields.map((field) => <label className="form-field" key={field.key}><span>{field.label}{field.required && <i> *</i>}</span>{field.key === "source_type" ? <select value={values.source_type} onChange={(event) => setValues({ ...values, source_type: event.target.value as SourceType })}><option value="website">Website</option><option value="rss">RSS</option><option value="news">News</option><option value="blog">Blog</option><option value="other">Other</option></select> : field.key === "ingestion_interval" ? <select value={values.ingestion_interval} onChange={(event) => setValues({ ...values, ingestion_interval: event.target.value as IngestionInterval })}>{(Object.keys(INGESTION_INTERVAL_LABELS) as IngestionInterval[]).map((interval) => <option value={interval} key={interval}>{INGESTION_INTERVAL_LABELS[interval]}</option>)}</select> : field.multiline ? <textarea rows={4} value={values.description} onChange={(event) => setValues({ ...values, description: event.target.value })} /> : <input required={field.required} type={field.key === "url" ? "url" : "text"} value={values[field.key as keyof Values] as string} onChange={(event) => setValues({ ...values, [field.key]: event.target.value })} placeholder={field.key === "url" ? "https://example.com/news" : field.key === "domain" ? "example.com" : ""} />}</label>)}{error && <p className="dialog-error" role="alert">{error}</p>}<footer><button className="secondary-button" type="button" disabled={saving} onClick={() => setEditing(undefined)}>Cancel</button><button className="primary-button" type="submit" disabled={saving}>{saving ? "Saving..." : editing ? "Save changes" : "Create"}</button></footer></form></section></div>}
    {deleting && <div className="dialog-backdrop"><section className="confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-title"><span className="section-kicker">DELETE RECORD</span><h2 id="delete-title">Delete {deleting.name}?</h2><p>This record will be removed from this workspace and its watchlist memberships will be cleared.</p>{error && <p className="dialog-error" role="alert">{error}</p>}<footer><button className="secondary-button" disabled={busy} onClick={() => setDeleting(null)}>Cancel</button><button className="danger-button" disabled={busy} onClick={() => void remove()}>{busy ? "Deleting..." : "Delete"}</button></footer></section></div>}
    {viewingEntity && (kind === "companies" || kind === "topics") && (
      <EntityIntelligenceDialog kind={kind === "companies" ? "company" : "topic"} entity={viewingEntity} onClose={() => setViewingEntity(null)} />
    )}
  </section>;
}

function IngestionStatus({ job }: { job?: CrawlJob }) {
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

function ScheduleCell({ source, job }: { source: Source; job?: CrawlJob }) {
  const nextRun = computeNextRun(job, source.ingestion_interval);
  return (
    <span className="ingestion-status-stack">
      <span>{INGESTION_INTERVAL_LABELS[source.ingestion_interval]}</span>
      {nextRun && <small className="ingestion-last-run">Next {formatDateTime(nextRun)}</small>}
    </span>
  );
}
