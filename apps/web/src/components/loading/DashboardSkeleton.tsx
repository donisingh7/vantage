import { LoadingStatus, SkeletonLine } from "./Skeleton";

/** Renders bare `.signal-row` skeletons — the caller already supplies the `.signal-list` wrapper. */
export function SignalListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <>
      <LoadingStatus label="Loading priority signals" />
      {Array.from({ length: count }).map((_, index) => (
        <div className="signal-row" key={index} aria-hidden="true">
          <span className="skeleton skeleton-circle" />
          <div className="signal-main">
            <SkeletonLine width="35%" height={9} />
            <div style={{ marginTop: 6 }}><SkeletonLine width="70%" height={13} /></div>
            <div style={{ marginTop: 4 }}><SkeletonLine width="90%" height={11} /></div>
          </div>
          <div className="signal-meta"><SkeletonLine width={28} height={16} /></div>
        </div>
      ))}
    </>
  );
}

/** Renders bare `.timeline-item` skeletons — the caller already supplies the `.timeline-list` wrapper. */
export function TimelineListSkeleton({ count = 3, label = "Loading recent activity" }: { count?: number; label?: string }) {
  return (
    <>
      <LoadingStatus label={label} />
      {Array.from({ length: count }).map((_, index) => (
        <div className="timeline-item" key={index} aria-hidden="true">
          <SkeletonLine width={38} height={9} />
          <div className="timeline-copy">
            <SkeletonLine width="30%" height={8} />
            <div style={{ marginTop: 4 }}><SkeletonLine width="68%" height={11} /></div>
          </div>
        </div>
      ))}
    </>
  );
}

export function DistributionSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="distribution-list" aria-hidden="true">
      {Array.from({ length: count }).map((_, index) => (
        <div className="distribution-row" key={index}>
          <SkeletonLine width="60%" height={9} />
          <span className="skeleton skeleton-track" />
          <SkeletonLine width={16} height={9} />
        </div>
      ))}
    </div>
  );
}

export function FocusListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <ul className="focus-list" aria-hidden="true">
      {Array.from({ length: count }).map((_, index) => (
        <li key={index}>
          <SkeletonLine width="55%" height={11} />
          <span className="skeleton skeleton-chip" />
        </li>
      ))}
    </ul>
  );
}
