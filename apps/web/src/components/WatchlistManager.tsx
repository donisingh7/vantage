"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { ChevronRight, Pencil, Plus, RefreshCw, Trash2, X } from "lucide-react";
import {
  ApiError, companiesApi, sourcesApi, topicsApi, watchlistsApi,
  type CatalogEntry, type CatalogSource, type Company, type Source, type Topic, type Watchlist, type WatchlistBootstrapResponse, type WatchlistDetail,
} from "@/lib/api";
import { WatchlistSkeleton } from "@/components/loading/WorkspacePageSkeleton";
import { LoadingStatus, SkeletonLine } from "@/components/loading/Skeleton";

type Kind = "companies" | "topics" | "sources";
type FormState = { name: string; description: string; is_active: boolean };
type Catalog = { companies: CatalogEntry[]; topics: CatalogEntry[]; sources: CatalogSource[] };
const blank = (): FormState => ({ name: "", description: "", is_active: true });

// -- Deployment compatibility fallback (404-only) ------------------------------------
// Only used when GET /watchlists/bootstrap/initial genuinely 404s (old Lambda, new frontend).
// (Two path segments deliberately -- a single-segment /watchlists/bootstrap would collide
// with the pre-Pass-3 GET /watchlists/{watchlist_id} route and 422 instead of 404 on an old Lambda.)
// Reconstructs the same shape from the four legacy calls it replaces; the initial detail
// is left null here and picked up by the existing selectedId effect (one GET
// /watchlists/{id}), matching this component's pre-Pass-3 request count exactly.
// Safe to delete once this endpoint is live on the deployed Lambda.
async function loadLegacyBootstrap(): Promise<WatchlistBootstrapResponse> {
  const [list, companies, topics, sources] = await Promise.all([
    watchlistsApi.list(), companiesApi.list(), topicsApi.list(), sourcesApi.list(),
  ]);
  return {
    watchlists: list.items,
    companies: companies.items.map((company) => ({ id: company.id, name: company.name })),
    topics: topics.items.map((topic) => ({ id: topic.id, name: topic.name })),
    sources: sources.items.map((source) => ({ id: source.id, name: source.name, url: source.url })),
    initial_detail: null,
  };
}
// -- End deployment compatibility fallback ------------------------------------------

export function WatchlistManager() {
  const [items, setItems] = useState<Watchlist[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<WatchlistDetail | null>(null);
  const [catalog, setCatalog] = useState<Catalog>({ companies: [], topics: [], sources: [] });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dialog, setDialog] = useState<"create" | "edit" | "delete" | null>(null);
  const [form, setForm] = useState<FormState>(blank);
  const [detailLoading, setDetailLoading] = useState(false);
  // Guards against out-of-order GET /watchlists/{id} responses: if the user selects A then
  // quickly B, and A's slower response resolves after B's, A must never overwrite B's
  // detail. Only the response whose sequence number still matches the latest dispatched
  // request may commit state.
  const detailRequestSeq = useRef(0);
  // An authoritative local detail update supersedes any in-flight GET /watchlists/{id}.
  // That request's finally block won't clear loading (its sequence is stale), so clear it here.
  function invalidateDetailRequest() {
    detailRequestSeq.current += 1;
    setDetailLoading(false);
  }

  async function bootstrap() {
    setLoading(true);
    try {
      let data: WatchlistBootstrapResponse;
      try {
        data = await watchlistsApi.bootstrap();
      } catch (cause) {
        if (cause instanceof ApiError && cause.status === 404) data = await loadLegacyBootstrap();
        else throw cause;
      }
      setItems(data.watchlists);
      setCatalog({ companies: data.companies, topics: data.topics, sources: data.sources });
      invalidateDetailRequest();
      setDetail(data.initial_detail);
      setSelectedId(data.initial_detail?.id ?? data.watchlists[0]?.id ?? null);
      setError("");
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not load watchlists."); }
    finally { setLoading(false); }
  }

  async function loadDetail(id: string) {
    const seq = ++detailRequestSeq.current;
    setDetailLoading(true);
    try {
      const result = await watchlistsApi.get(id);
      if (seq !== detailRequestSeq.current) return; // superseded by a newer selection
      setDetail(result);
    } catch (cause) {
      if (seq !== detailRequestSeq.current) return;
      setError(cause instanceof ApiError ? cause.message : "Could not load watchlist details.");
    } finally {
      if (seq === detailRequestSeq.current) setDetailLoading(false);
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only bootstrap
  useEffect(() => { void bootstrap(); }, []);
  useEffect(() => {
    if (!selectedId) { invalidateDetailRequest(); setDetail(null); return; }
    if (detail?.id === selectedId) return; // bootstrap/mutation already supplied this detail
    void loadDetail(selectedId); // bumps detailRequestSeq itself, invalidating any prior in-flight request
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  function openCreate() { setForm(blank()); setDialog("create"); setError(""); }
  function openEdit(item: Watchlist) { setForm({ name: item.name, description: item.description ?? "", is_active: item.is_active }); setDialog("edit"); setError(""); }

  function patchWatchlistInList(updated: Watchlist) {
    setItems((prev) => prev.map((item) => (item.id === updated.id ? updated : item)).sort((a, b) => a.name.localeCompare(b.name)));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (dialog === "edit" && selectedId) {
        const updated = await watchlistsApi.update(selectedId, form);
        patchWatchlistInList(updated);
        invalidateDetailRequest();
        setDetail((prev) => (prev ? { ...prev, ...updated } : prev));
        setNotice("Watchlist updated.");
      } else {
        const created = await watchlistsApi.create(form);
        setItems((prev) => [...prev, created].sort((a, b) => a.name.localeCompare(b.name)));
        invalidateDetailRequest();
        setDetail({ ...created, companies: [], topics: [], sources: [] });
        setSelectedId(created.id);
        setNotice("Watchlist created.");
      }
      setDialog(null);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not save watchlist."); }
    finally { setBusy(false); }
  }

  async function removeWatchlist() {
    if (!selectedId) return;
    setBusy(true);
    try {
      await watchlistsApi.delete(selectedId);
      const remaining = items.filter((item) => item.id !== selectedId);
      setItems(remaining);
      setDialog(null); setNotice("Watchlist deleted.");
      setSelectedId(remaining[0]?.id ?? null); // the selectedId effect loads its detail if needed
    }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not delete watchlist."); }
    finally { setBusy(false); }
  }

  async function toggleActive(item: Watchlist) {
    setBusy(true);
    try {
      const updated = await watchlistsApi.update(item.id, { is_active: !item.is_active });
      patchWatchlistInList(updated);
      invalidateDetailRequest();
      setDetail((prev) => (prev && prev.id === updated.id ? { ...prev, ...updated } : prev));
      setNotice(`Watchlist ${item.is_active ? "paused" : "activated"}.`);
    }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not update watchlist."); }
    finally { setBusy(false); }
  }

  async function changeMember(kind: Kind, id: string, add: boolean) {
    if (!selectedId) return;
    setBusy(true); setError("");
    try {
      const updated = add ? await watchlistsApi.addMember(selectedId, kind, id) : await watchlistsApi.removeMember(selectedId, kind, id);
      invalidateDetailRequest();
      setDetail(updated);
      patchWatchlistInList(updated); // WatchlistDetail carries every Watchlist field, just also the member arrays
      setNotice(`${kind.slice(0, -1)} ${add ? "added to" : "removed from"} watchlist.`);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not change watchlist membership."); }
    finally { setBusy(false); }
  }

  return <section className="management-page">
    <header className="management-heading"><div><div className="eyebrow"><span className="eyebrow-rule" />MONITORING</div><h1>Watchlists</h1><p>Bring companies, themes, and sources together around a shared focus.</p></div><button className="primary-button" onClick={openCreate}><Plus size={16} /> New watchlist</button></header>
    {notice && <div className="feedback feedback-success" role="status">{notice}<button aria-label="Dismiss message" onClick={() => setNotice("")}><X size={14} /></button></div>}
    {error && !dialog && <div className="feedback feedback-error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}><X size={14} /></button></div>}
    {loading ? <WatchlistSkeleton /> : items.length === 0 ? <div className="empty-surface"><div className="empty-symbol"><Plus size={19} /></div><h2>Start with a focused list</h2><p>Create a watchlist, then add companies, topics, and sources from your workspace.</p><button className="secondary-button" onClick={openCreate}>Create first watchlist</button></div> : <div className="watchlist-layout content-fade-in">
      <aside className="watchlist-list" aria-label="Watchlists">{items.map((item) => <button className={`watchlist-choice ${item.id === selectedId ? "watchlist-choice-active" : ""}`} key={item.id} onClick={() => setSelectedId(item.id)}><span className="watchlist-choice-copy"><strong>{item.name}</strong><small>{item.counts.companies} companies · {item.counts.topics} topics · {item.counts.sources} sources</small></span><span className={`watchlist-state ${item.is_active ? "state-on" : "state-off"}`}>{item.is_active ? "Active" : "Paused"}</span><ChevronRight size={15} /></button>)}</aside>
      {detail && detail.id === selectedId ? <div className="watchlist-detail"><header className="watchlist-detail-heading"><div><span className="section-kicker">{detail.is_active ? "ACTIVE MONITORING" : "PAUSED"}</span><h2>{detail.name}</h2><p>{detail.description || "No description added."}</p></div><div className="row-actions"><button className="secondary-button compact-button" disabled={busy} onClick={() => void toggleActive(detail)}>{detail.is_active ? "Pause" : "Activate"}</button><button className="icon-action" aria-label="Edit watchlist" onClick={() => openEdit(detail)}><Pencil size={15} /></button><button className="icon-action action-danger" aria-label="Delete watchlist" onClick={() => setDialog("delete")}><Trash2 size={15} /></button></div></header>
        <div className="watchlist-counts"><Count label="Companies" value={detail.counts.companies} /><Count label="Topics" value={detail.counts.topics} /><Count label="Sources" value={detail.counts.sources} /></div>
        <MemberSection kind="companies" catalog={catalog.companies} selected={detail.companies} disabled={busy} onAdd={(id) => void changeMember("companies", id, true)} onRemove={(id) => void changeMember("companies", id, false)} />
        <MemberSection kind="topics" catalog={catalog.topics} selected={detail.topics} disabled={busy} onAdd={(id) => void changeMember("topics", id, true)} onRemove={(id) => void changeMember("topics", id, false)} />
        <MemberSection kind="sources" catalog={catalog.sources} selected={detail.sources} disabled={busy} onAdd={(id) => void changeMember("sources", id, true)} onRemove={(id) => void changeMember("sources", id, false)} />
      </div> : detailLoading ? <WatchlistDetailPaneSkeleton /> : null}
    </div>}
    {dialog && <div className="dialog-backdrop"><section className="form-dialog" role={dialog === "delete" ? "alertdialog" : "dialog"} aria-modal="true" aria-labelledby="watchlist-dialog-title">{dialog === "delete" ? <><span className="section-kicker">DELETE WATCHLIST</span><h2 id="watchlist-dialog-title">Delete {detail?.name}?</h2><p>This only deletes the watchlist. Companies, topics, and sources remain in your workspace.</p>{error && <p className="dialog-error" role="alert">{error}</p>}<footer><button className="secondary-button" disabled={busy} onClick={() => setDialog(null)}>Cancel</button><button className="danger-button" disabled={busy} aria-busy={busy} onClick={() => void removeWatchlist()}>{busy ? <RefreshCw size={14} className="spin-icon" /> : null}{busy ? "Deleting..." : "Delete watchlist"}</button></footer></> : <><header><div><span className="section-kicker">{dialog === "edit" ? "EDIT WATCHLIST" : "NEW WATCHLIST"}</span><h2 id="watchlist-dialog-title">{dialog === "edit" ? "Watchlist details" : "Create a watchlist"}</h2></div><button className="icon-action" aria-label="Close dialog" onClick={() => setDialog(null)}><X size={18} /></button></header><form onSubmit={(event) => void submit(event)}><label className="form-field"><span>Name *</span><input required maxLength={160} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label className="form-field"><span>Description</span><textarea rows={3} maxLength={2000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label><label className="checkbox-field"><input type="checkbox" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} /><span>Active</span></label>{error && <p className="dialog-error" role="alert">{error}</p>}<footer><button className="secondary-button" type="button" disabled={busy} onClick={() => setDialog(null)}>Cancel</button><button className="primary-button" type="submit" disabled={busy} aria-busy={busy}>{busy ? <RefreshCw size={14} className="spin-icon" /> : null}{busy ? "Saving..." : dialog === "edit" ? "Save changes" : "Create watchlist"}</button></footer></form></>}</section></div>}
  </section>;
}

function Count({ label, value }: { label: string; value: number }) { return <div className="watchlist-count"><strong>{value}</strong><span>{label}</span></div>; }

// Right-pane-only skeleton shown while a newly-selected watchlist's detail is loading --
// the sidebar list stays fully interactive/stable, and the stale previous detail is never
// shown (see the detailRequestSeq guard above this component).
function WatchlistDetailPaneSkeleton() {
  return (
    <div className="watchlist-detail">
      <LoadingStatus label="Loading watchlist details" />
      <div aria-hidden="true">
        <SkeletonLine width="40%" height={22} />
        <div className="watchlist-counts" style={{ marginTop: 22 }}>
          {Array.from({ length: 3 }).map((_, index) => (
            <div className="watchlist-count" key={index}>
              <SkeletonLine width={30} height={22} />
              <div style={{ marginTop: 6 }}><SkeletonLine width="70%" height={9} /></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function MemberSection({ kind, catalog, selected, disabled, onAdd, onRemove }: { kind: Kind; catalog: (CatalogEntry | CatalogSource)[]; selected: (Company | Topic | Source)[]; disabled: boolean; onAdd: (id: string) => void; onRemove: (id: string) => void }) {
  const [candidate, setCandidate] = useState("");
  const ids = new Set(selected.map((item) => item.id));
  const available = catalog.filter((item) => !ids.has(item.id));
  return <section className="member-section"><header><div><h3>{kind[0].toUpperCase() + kind.slice(1)}</h3><span>{selected.length} linked</span></div><div className="member-add"><select value={candidate} aria-label={`Choose ${kind.slice(0, -1)} to add`} onChange={(event) => setCandidate(event.target.value)}><option value="">Add {kind.slice(0, -1)}...</option>{available.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><button className="icon-action member-add-button" title={`Add ${kind.slice(0, -1)}`} aria-label={`Add ${kind.slice(0, -1)}`} disabled={!candidate || disabled} onClick={() => { onAdd(candidate); setCandidate(""); }}><Plus size={16} /></button></div></header>{selected.length === 0 ? <p className="member-empty">No {kind} added to this watchlist.</p> : <ul>{selected.map((item) => <li key={item.id}><span>{item.name}</span>{kind === "sources" && <a href={(item as Source).url} target="_blank" rel="noopener noreferrer">Open source</a>}<button className="icon-action action-danger" title={`Remove ${item.name}`} aria-label={`Remove ${item.name}`} disabled={disabled} onClick={() => onRemove(item.id)}><X size={15} /></button></li>)}</ul>}</section>;
}
