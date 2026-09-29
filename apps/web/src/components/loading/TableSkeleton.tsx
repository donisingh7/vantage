import { LoadingStatus, SkeletonLine } from "./Skeleton";

export function TableSkeleton({ columns, rows = 6, label = "Loading records" }: { columns: number; rows?: number; label?: string }) {
  return (
    <>
      <LoadingStatus label={label} />
      <div className="table-wrap" aria-hidden="true">
        <table className="resource-table">
          <thead>
            <tr>
              {Array.from({ length: columns }).map((_, column) => (
                <th key={column}><SkeletonLine width="70%" height={10} /></th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: rows }).map((_, row) => (
              <tr key={row}>
                {Array.from({ length: columns }).map((_, column) => (
                  <td key={column}><SkeletonLine width={column === 0 ? "80%" : "55%"} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
