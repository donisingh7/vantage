import { LoadingStatus, SkeletonLine } from "./Skeleton";

export function CardGridSkeleton({ count = 6, label = "Loading signals" }: { count?: number; label?: string }) {
  return (
    <>
      <LoadingStatus label={label} />
      <div className="signal-card-grid" aria-hidden="true">
        {Array.from({ length: count }).map((_, index) => (
          <div className="signal-card skeleton-card" key={index}>
            <div className="signal-card-heading">
              <SkeletonLine width={70} height={16} />
              <SkeletonLine width={54} height={16} />
            </div>
            <SkeletonLine width="75%" height={15} />
            <SkeletonLine height={11} />
            <SkeletonLine width="85%" height={11} />
            <div className="signal-card-meta">
              <SkeletonLine width={60} height={9} />
              <SkeletonLine width={70} height={9} />
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

export function DocumentListSkeleton({ count = 3, label = "Loading collected documents" }: { count?: number; label?: string }) {
  return (
    <>
      <LoadingStatus label={label} />
      <div className="document-list" aria-hidden="true">
        {Array.from({ length: count }).map((_, index) => (
          <div className="document-card skeleton-card" key={index}>
            <div className="document-card-heading">
              <SkeletonLine width="55%" height={17} />
              <SkeletonLine width={70} height={12} />
            </div>
            <div className="document-meta">
              <SkeletonLine width={90} height={9} />
              <SkeletonLine width={110} height={9} />
              <SkeletonLine width={100} height={9} />
            </div>
            <SkeletonLine height={11} />
            <SkeletonLine width="70%" height={11} />
          </div>
        ))}
      </div>
    </>
  );
}
