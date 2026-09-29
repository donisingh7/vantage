export function Skeleton({
  className = "",
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return <span className={`skeleton ${className}`} style={style} />;
}

export function SkeletonLine({ width = "100%", height }: { width?: string | number; height?: number }) {
  return <Skeleton className="skeleton-line" style={{ width, height }} />;
}

/** Visually-hidden status text announced to assistive tech while a skeleton (aria-hidden) is shown. */
export function LoadingStatus({ label }: { label: string }) {
  return (
    <span className="visually-hidden" role="status">
      {label}
    </span>
  );
}
