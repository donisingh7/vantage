import { LoadingStatus, SkeletonLine } from "./Skeleton";

/** Generic route-level fallback for the App Router `loading.tsx` boundary — shown briefly
 * while a workspace section's code/data starts loading, before that section's own,
 * more specifically-shaped skeleton (table, cards, dashboard, ...) takes over. */
export function WorkspacePageSkeleton() {
  return (
    <div className="management-page" aria-hidden="true">
      <LoadingStatus label="Loading workspace" />
      <header className="management-heading">
        <div>
          <SkeletonLine width={120} height={10} />
          <div style={{ marginTop: 12 }}><SkeletonLine width={220} height={30} /></div>
          <div style={{ marginTop: 10 }}><SkeletonLine width={320} height={13} /></div>
        </div>
      </header>
      <div className="skeleton-block-grid">
        <span className="skeleton skeleton-block" />
        <span className="skeleton skeleton-block" />
        <span className="skeleton skeleton-block" />
      </div>
    </div>
  );
}

export function SettingsSkeleton() {
  return (
    <div className="settings-grid" aria-hidden="true">
      <LoadingStatus label="Loading settings" />
      {Array.from({ length: 2 }).map((_, index) => (
        <div className="settings-card" key={index}>
          <SkeletonLine width={70} height={9} />
          <div style={{ marginTop: 14 }}><SkeletonLine width="50%" height={21} /></div>
          <div style={{ marginTop: 18 }}><SkeletonLine height={13} /></div>
          <div style={{ marginTop: 10 }}><SkeletonLine height={13} /></div>
        </div>
      ))}
    </div>
  );
}

export function WatchlistSkeleton() {
  return (
    <div className="watchlist-layout" aria-hidden="true">
      <LoadingStatus label="Loading watchlists" />
      <div className="watchlist-list">
        {Array.from({ length: 4 }).map((_, index) => (
          <div className="watchlist-choice" key={index}>
            <span className="skeleton-choice-copy">
              <SkeletonLine width="65%" height={12} />
              <div style={{ marginTop: 5 }}><SkeletonLine width="85%" height={9} /></div>
            </span>
          </div>
        ))}
      </div>
      <div className="watchlist-detail">
        <SkeletonLine width={140} height={9} />
        <div style={{ marginTop: 10 }}><SkeletonLine width="40%" height={22} /></div>
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
