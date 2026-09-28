"use client";

import { useEffect, useState, type FormEvent } from "react";
import { ChevronRight, Pencil, Plus, Trash2, X } from "lucide-react";
import { ApiError, companiesApi, sourcesApi, topicsApi, watchlistsApi, type Company, type Source, type Topic, type Watchlist, type WatchlistDetail } from "@/lib/api";

type Kind = "companies" | "topics" | "sources";
type FormState = { name: string; description: string; is_active: boolean };
const blank = (): FormState => ({ name: "", description: "", is_active: true });

export function WatchlistManager() {
  const [items, setItems] = useState<Watchlist[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<WatchlistDetail | null>(null);
  const [catalog, setCatalog] = useState<{ companies: Company[]; topics: Topic[]; sources: Source[] }>({ companies: [], topics: [], sources: [] });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dialog, setDialog] = useState<"create" | "edit" | "delete" | null>(null);
  const [form, setForm] = useState<FormState>(blank);

  async function refreshLists(preferredId: string | null = selectedId) {
    setLoading(true);
    try {
      const [list, companies, topics, sources] = await Promise.all([watchlistsApi.list(), companiesApi.list(), topicsApi.list(), sourcesApi.list()]);
      setItems(list.items);
      setCatalog({ companies: companies.items, topics: topics.items, sources: sources.items });
      const nextId = preferredId && list.items.some((item) => item.id === preferredId) ? preferredId : list.items[0]?.id ?? null;
      setSelectedId(nextId);
      setError("");
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not load watchlists."); }
    finally { setLoading(false); }
  }

  async function loadDetail(id: string) {
    try { setDetail(await watchlistsApi.get(id)); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not load watchlist details."); }
  }

  useEffect(() => { void refreshLists(null); }, []);
  useEffect(() => { if (selectedId) void loadDetail(selectedId); else setDetail(null); }, [selectedId]);

  function openCreate() { setForm(blank()); setDialog("create"); setError(""); }
  function openEdit(item: Watchlist) { setForm({ name: item.name, description: item.description ?? "", is_active: item.is_active }); setDialog("edit"); setError(""); }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (dialog === "edit" && selectedId) { await watchlistsApi.update(selectedId, form); setNotice("Watchlist updated."); }
      else { const created = await watchlistsApi.create(form); setSelectedId(created.id); setNotice("Watchlist created."); }
      setDialog(null);
      await refreshLists(dialog === "edit" ? selectedId : null);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not save watchlist."); }
    finally { setBusy(false); }
  }

  async function removeWatchlist() {
    if (!selectedId) return;
    setBusy(true);
    try { await watchlistsApi.delete(selectedId); setDialog(null); setNotice("Watchlist deleted."); await refreshLists(null); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not delete watchlist."); }
    finally { setBusy(false); }
  }

  async function toggleActive(item: Watchlist) {
    setBusy(true);
    try { await watchlistsApi.update(item.id, { is_active: !item.is_active }); setNotice(`Watchlist ${item.is_active ? "paused" : "activated"}.`); await refreshLists(item.id); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not update watchlist."); }
    finally { setBusy(false); }
  }

  async function changeMember(kind: Kind, id: string, add: boolean) {
    if (!selectedId) return;
    setBusy(true); setError("");
    try {
      const updated = add ? await watchlistsApi.addMember(selectedId, kind, id) : await watchlistsApi.removeMember(selectedId, kind, id);
      setDetail(updated); setNotice(`${kind.slice(0, -1)} ${add ? "added to" : "removed from"} watchlist.`);
      setItems((await watchlistsApi.list()).items);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Could not change watchlist membership."); }
    finally { setBusy(false); }
  }

  return <section className="management-page">
    <header className="management-heading"><div><div className="eyebrow"><span className="eyebrow-rule" />MONITORING</div><h1>Watchlists</h1><p>Bring companies, themes, and sources together around a shared focus.</p></div><button className="primary-button" onClick={openCreate}><Plus size={16} /> New watchlist</button></header>
    {notice && <div className="feedback feedback-success" role="status">{notice}<button aria-label="Dismiss message" onClick={() => setNotice("")}><X size={14} /></button></div>}
    {error && !dialog && <div className="feedback feedback-error" role="alert">{error}<button aria-label="Dismiss error" onClick={() => setError("")}><X size={14} /></button></div>}
    {loading ? <div className="loading-surface">Loading watchlists...</div> : items.length === 0 ? <div className="empty-surface"><div className="empty-symbol"><Plus size={19} /></div><h2>Start with a focused list</h2><p>Create a watchlist, then add companies, topics, and sources from your workspace.</p><button className="secondary-button" onClick={openCreate}>Create first watchlist</button></div> : <div className="watchlist-layout">
      <aside className="watchlist-list" aria-label="Watchlists">{items.map((item) => <button className={`watchlist-choice ${item.id === selectedId ? "watchlist-choice-active" : ""}`} key={item.id} onClick={() => setSelectedId(item.id)}><span className="watchlist-choice-copy"><strong>{item.name}</strong><small>{item.counts.companies} companies · {item.counts.topics} topics · {item.counts.sources} sources</small></span><span className={`watchlist-state ${item.is_active ? "state-on" : "state-off"}`}>{item.is_active ? "Active" : "Paused"}</span><ChevronRight size={15} /></button>)}</aside>
      {detail && <div className="watchlist-detail"><header className="watchlist-detail-heading"><div><span className="section-kicker">{detail.is_active ? "ACTIVE MONITORING" : "PAUSED"}</span><h2>{detail.name}</h2><p>{detail.description || "No description added."}</p></div><div className="row-actions"><button className="secondary-button compact-button" disabled={busy} onClick={() => void toggleActive(detail)}>{detail.is_active ? "Pause" : "Activate"}</button><button className="icon-action" aria-label="Edit watchlist" onClick={() => openEdit(detail)}><Pencil size={15} /></button><button className="icon-action action-danger" aria-label="Delete watchlist" onClick={() => setDialog("delete")}><Trash2 size={15} /></button></div></header>
        <div className="watchlist-counts"><Count label="Companies" value={detail.counts.companies} /><Count label="Topics" value={detail.counts.topics} /><Count label="Sources" value={detail.counts.sources} /></div>
        {(["companies", "topics", "sources"] as const).map((kind) => <MemberSection key={kind} kind={kind} catalog={catalog[kind]} selected={detail[kind]} disabled={busy} onAdd={(id) => void changeMember(kind, id, true)} onRemove={(id) => void changeMember(kind, id, false)} />)}
      </div>}
    </div>}
    {dialog && <div className="dialog-backdrop"><section className="form-dialog" role={dialog === "delete" ? "alertdialog" : "dialog"} aria-modal="true" aria-labelledby="watchlist-dialog-title">{dialog === "delete" ? <><span className="section-kicker">DELETE WATCHLIST</span><h2 id="watchlist-dialog-title">Delete {detail?.name}?</h2><p>This only deletes the watchlist. Companies, topics, and sources remain in your workspace.</p>{error && <p className="dialog-error" role="alert">{error}</p>}<footer><button className="secondary-button" disabled={busy} onClick={() => setDialog(null)}>Cancel</button><button className="danger-button" disabled={busy} onClick={() => void removeWatchlist()}>{busy ? "Deleting..." : "Delete watchlist"}</button></footer></> : <><header><div><span className="section-kicker">{dialog === "edit" ? "EDIT WATCHLIST" : "NEW WATCHLIST"}</span><h2 id="watchlist-dialog-title">{dialog === "edit" ? "Watchlist details" : "Create a watchlist"}</h2></div><button className="icon-action" aria-label="Close dialog" onClick={() => setDialog(null)}><X size={18} /></button></header><form onSubmit={(event) => void submit(event)}><label className="form-field"><span>Name *</span><input required maxLength={160} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label><label className="form-field"><span>Description</span><textarea rows={3} maxLength={2000} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label><label className="checkbox-field"><input type="checkbox" checked={form.is_active} onChange={(event) => setForm({ ...form, is_active: event.target.checked })} /><span>Active</span></label>{error && <p className="dialog-error" role="alert">{error}</p>}<footer><button className="secondary-button" type="button" disabled={busy} onClick={() => setDialog(null)}>Cancel</button><button className="primary-button" type="submit" disabled={busy}>{busy ? "Saving..." : dialog === "edit" ? "Save changes" : "Create watchlist"}</button></footer></form></>}</section></div>}
  </section>;
}

function Count({ label, value }: { label: string; value: number }) { return <div className="watchlist-count"><strong>{value}</strong><span>{label}</span></div>; }

function MemberSection({ kind, catalog, selected, disabled, onAdd, onRemove }: { kind: Kind; catalog: (Company | Topic | Source)[]; selected: (Company | Topic | Source)[]; disabled: boolean; onAdd: (id: string) => void; onRemove: (id: string) => void }) {
  const [candidate, setCandidate] = useState("");
  const ids = new Set(selected.map((item) => item.id));
  const available = catalog.filter((item) => !ids.has(item.id));
  return <section className="member-section"><header><div><h3>{kind[0].toUpperCase() + kind.slice(1)}</h3><span>{selected.length} linked</span></div><div className="member-add"><select value={candidate} aria-label={`Choose ${kind.slice(0, -1)} to add`} onChange={(event) => setCandidate(event.target.value)}><option value="">Add {kind.slice(0, -1)}...</option>{available.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select><button className="icon-action member-add-button" title={`Add ${kind.slice(0, -1)}`} aria-label={`Add ${kind.slice(0, -1)}`} disabled={!candidate || disabled} onClick={() => { onAdd(candidate); setCandidate(""); }}><Plus size={16} /></button></div></header>{selected.length === 0 ? <p className="member-empty">No {kind} added to this watchlist.</p> : <ul>{selected.map((item) => <li key={item.id}><span>{item.name}</span>{kind === "sources" && <a href={(item as Source).url} target="_blank" rel="noopener noreferrer">Open source</a>}<button className="icon-action action-danger" title={`Remove ${item.name}`} aria-label={`Remove ${item.name}`} disabled={disabled} onClick={() => onRemove(item.id)}><X size={15} /></button></li>)}</ul>}</section>;
}
