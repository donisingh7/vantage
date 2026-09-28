export type SystemInfo = {
  name: string;
  environment: string;
  version: string;
  llm_provider: string;
  embedding_provider: string;
};

export type Workspace = { id: string; name: string; slug: string; created_at: string; updated_at: string };
export type User = { id: string; email: string; display_name: string; is_active: boolean };
export type CurrentIdentity = { user: User; workspace: Workspace; role: string };
export type WorkspaceSummary = {
  watchlists: number;
  companies: number;
  topics: number;
  sources: number;
  active_watchlists: number;
  active_sources: number;
};
export type ListResponse<T> = { items: T[]; total: number };
export type Company = {
  id: string; workspace_id: string; name: string; domain: string | null;
  description: string | null; created_at: string; updated_at: string; watchlist_count: number;
};
export type Topic = {
  id: string; workspace_id: string; name: string; description: string | null;
  created_at: string; updated_at: string; watchlist_count: number;
};
export type SourceType = "website" | "rss" | "news" | "blog" | "other";
export type IngestionInterval = "manual" | "every_6_hours" | "every_12_hours" | "every_24_hours";
export type Source = {
  id: string; workspace_id: string; name: string; url: string; source_type: SourceType;
  is_active: boolean; ingestion_interval: IngestionInterval;
  created_at: string; updated_at: string; watchlist_count: number;
};
export type Watchlist = {
  id: string; workspace_id: string; name: string; description: string | null;
  is_active: boolean; created_at: string; updated_at: string;
  counts: { companies: number; topics: number; sources: number };
};
export type WatchlistDetail = Watchlist & {
  companies: Company[]; topics: Topic[]; sources: Source[];
};
export type CrawlJobStatus = "queued" | "running" | "completed" | "failed";
export type CrawlJob = {
  id: string; workspace_id: string; source_id: string; status: CrawlJobStatus;
  started_at: string | null; completed_at: string | null; error_message: string | null;
  documents_found: number; documents_created: number; documents_skipped: number;
  pages_discovered: number; pages_failed: number; created_at: string; updated_at: string;
};
export type AnalysisStatus = "completed" | "irrelevant" | "failed";
export type Document = {
  id: string; workspace_id: string; source_id: string; canonical_url: string;
  title: string | null; excerpt: string | null; author: string | null;
  published_at: string | null; fetched_at: string; created_at: string; updated_at: string;
  analysis_status: AnalysisStatus | null; signal_id: string | null; indexed: boolean;
};
export type SignalType =
  | "product" | "competitor" | "funding" | "partnership" | "acquisition" | "leadership"
  | "regulation" | "technology" | "market" | "pricing" | "risk" | "other";
export type Sentiment = "positive" | "neutral" | "negative" | "mixed";
export type IntelligenceSignal = {
  id: string; workspace_id: string; document_id: string;
  company_id: string | null; topic_id: string | null;
  signal_type: SignalType | null; title: string | null; executive_summary: string | null;
  relevance_score: number; importance_score: number; sentiment: Sentiment | null;
  key_entities: string[]; key_points: string[]; business_impact: string | null;
  confidence_score: number; evidence_excerpt: string | null;
  analysis_status: AnalysisStatus; analyzed_at: string; created_at: string; updated_at: string;
};
export type IndexResult = { document_id: string; chunks_created: number; total_chunks: number; skipped: boolean };
export type SearchResult = {
  document_id: string; title: string | null; source_name: string; source_url: string;
  canonical_url: string; excerpt: string; similarity: number;
};
export type AskCitation = {
  document_id: string; title: string | null; source_name: string; url: string;
  excerpt: string; similarity: number;
};
export type AskResponse = {
  answer: string; citations: AskCitation[]; retrieved_count: number; provider: string; grounded: boolean;
};

const apiBaseUrl = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}), ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Vantage API is currently unavailable.", 0);
  }

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { error?: { message?: string; code?: string } }
      | null;
    throw new ApiError(
      payload?.error?.message ?? "The request could not be completed.",
      response.status,
      payload?.error?.code,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function queryPath(path: string, search?: string): string {
  return search?.trim() ? `${path}?search=${encodeURIComponent(search.trim())}` : path;
}

function jsonBody(value: unknown): string {
  return JSON.stringify(value);
}

export function getSystemInfo(): Promise<SystemInfo> {
  return request<SystemInfo>("/api/v1/system/info");
}

export const workspaceApi = {
  me: () => request<CurrentIdentity>("/api/v1/me"),
  list: () => request<Workspace[]>("/api/v1/workspaces"),
  get: (id: string) => request<Workspace>(`/api/v1/workspaces/${id}`),
  summary: () => request<WorkspaceSummary>("/api/v1/workspace/summary"),
};

export const companiesApi = {
  list: (search?: string) => request<ListResponse<Company>>(queryPath("/api/v1/companies", search)),
  get: (id: string) => request<Company>(`/api/v1/companies/${id}`),
  create: (data: { name: string; domain?: string | null; description?: string | null }) =>
    request<Company>("/api/v1/companies", { method: "POST", body: jsonBody(data) }),
  update: (id: string, data: Partial<Pick<Company, "name" | "domain" | "description">>) =>
    request<Company>(`/api/v1/companies/${id}`, { method: "PATCH", body: jsonBody(data) }),
  delete: (id: string) => request<void>(`/api/v1/companies/${id}`, { method: "DELETE" }),
};

export const topicsApi = {
  list: (search?: string) => request<ListResponse<Topic>>(queryPath("/api/v1/topics", search)),
  get: (id: string) => request<Topic>(`/api/v1/topics/${id}`),
  create: (data: { name: string; description?: string | null }) =>
    request<Topic>("/api/v1/topics", { method: "POST", body: jsonBody(data) }),
  update: (id: string, data: Partial<Pick<Topic, "name" | "description">>) =>
    request<Topic>(`/api/v1/topics/${id}`, { method: "PATCH", body: jsonBody(data) }),
  delete: (id: string) => request<void>(`/api/v1/topics/${id}`, { method: "DELETE" }),
};

export const sourcesApi = {
  list: (search?: string) => request<ListResponse<Source>>(queryPath("/api/v1/sources", search)),
  get: (id: string) => request<Source>(`/api/v1/sources/${id}`),
  create: (data: { name: string; url: string; source_type: SourceType; is_active?: boolean; ingestion_interval?: IngestionInterval }) =>
    request<Source>("/api/v1/sources", { method: "POST", body: jsonBody(data) }),
  update: (id: string, data: Partial<Pick<Source, "name" | "url" | "source_type" | "is_active" | "ingestion_interval">>) =>
    request<Source>(`/api/v1/sources/${id}`, { method: "PATCH", body: jsonBody(data) }),
  delete: (id: string) => request<void>(`/api/v1/sources/${id}`, { method: "DELETE" }),
};

export const watchlistsApi = {
  list: (search?: string) => request<ListResponse<Watchlist>>(queryPath("/api/v1/watchlists", search)),
  get: (id: string) => request<WatchlistDetail>(`/api/v1/watchlists/${id}`),
  create: (data: { name: string; description?: string | null; is_active?: boolean }) =>
    request<Watchlist>("/api/v1/watchlists", { method: "POST", body: jsonBody(data) }),
  update: (id: string, data: Partial<Pick<Watchlist, "name" | "description" | "is_active">>) =>
    request<Watchlist>(`/api/v1/watchlists/${id}`, { method: "PATCH", body: jsonBody(data) }),
  delete: (id: string) => request<void>(`/api/v1/watchlists/${id}`, { method: "DELETE" }),
  addMember: (id: string, kind: "companies" | "topics" | "sources", memberId: string) =>
    request<WatchlistDetail>(`/api/v1/watchlists/${id}/${kind}/${memberId}`, { method: "PUT" }),
  removeMember: (id: string, kind: "companies" | "topics" | "sources", memberId: string) =>
    request<WatchlistDetail>(`/api/v1/watchlists/${id}/${kind}/${memberId}`, { method: "DELETE" }),
};

export const ingestionApi = {
  run: (sourceId: string) => request<CrawlJob>(`/api/v1/sources/${sourceId}/ingest`, { method: "POST" }),
  listJobs: (sourceId?: string) =>
    request<ListResponse<CrawlJob>>(`/api/v1/ingestion/jobs${sourceId ? `?source_id=${sourceId}` : ""}`),
  getJob: (jobId: string) => request<CrawlJob>(`/api/v1/ingestion/jobs/${jobId}`),
};

export const documentsApi = {
  list: (sourceId?: string) =>
    request<ListResponse<Document>>(`/api/v1/documents${sourceId ? `?source_id=${sourceId}` : ""}`),
  analyze: (documentId: string, force = false) =>
    request<IntelligenceSignal>(`/api/v1/documents/${documentId}/analyze${force ? "?force=true" : ""}`, { method: "POST" }),
  index: (documentId: string, force = false) =>
    request<IndexResult>(`/api/v1/documents/${documentId}/index${force ? "?force=true" : ""}`, { method: "POST" }),
};

export const searchApi = {
  search: (q: string, topK = 5) =>
    request<{ query: string; results: SearchResult[] }>(`/api/v1/search?q=${encodeURIComponent(q)}&top_k=${topK}`),
  indexPending: (limit = 5) =>
    request<{ indexed: number; results: IndexResult[] }>("/api/v1/search/index-pending", {
      method: "POST",
      body: jsonBody({ limit }),
    }),
};

export const askApi = {
  ask: (question: string, topK = 5) =>
    request<AskResponse>("/api/v1/ask", { method: "POST", body: jsonBody({ question, top_k: topK }) }),
};

export const intelligenceApi = {
  analyzePending: (limit = 5) =>
    request<{ analyzed: number; signals: IntelligenceSignal[] }>("/api/v1/intelligence/analyze-pending", {
      method: "POST",
      body: jsonBody({ limit }),
    }),
  listSignals: (params?: {
    company_id?: string; topic_id?: string; signal_type?: SignalType; sentiment?: Sentiment; min_importance?: number;
  }) => {
    const query = new URLSearchParams();
    if (params?.company_id) query.set("company_id", params.company_id);
    if (params?.topic_id) query.set("topic_id", params.topic_id);
    if (params?.signal_type) query.set("signal_type", params.signal_type);
    if (params?.sentiment) query.set("sentiment", params.sentiment);
    if (params?.min_importance !== undefined) query.set("min_importance", String(params.min_importance));
    const search = query.toString();
    return request<ListResponse<IntelligenceSignal>>(`/api/v1/intelligence/signals${search ? `?${search}` : ""}`);
  },
  getSignal: (id: string) => request<IntelligenceSignal>(`/api/v1/intelligence/signals/${id}`),
};