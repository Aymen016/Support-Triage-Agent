export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-skeleton rounded bg-[var(--color-border)] ${className}`} />;
}

export function EmailListItemSkeleton() {
  return (
    <div className="px-4 py-2.5 border-b border-[var(--color-border)] flex items-center gap-2.5">
      <Skeleton className="w-2 h-2 rounded-full shrink-0" />
      <div className="flex-1 min-w-0 space-y-1.5">
        <div className="flex items-center justify-between gap-2">
          <Skeleton className="h-3.5 w-32" />
          <Skeleton className="h-3 w-10" />
        </div>
        <Skeleton className="h-3 w-full max-w-56" />
        <div className="flex items-center gap-2 pt-0.5">
          <Skeleton className="h-4 w-14" />
          <Skeleton className="h-1.5 w-10" />
        </div>
      </div>
    </div>
  );
}

export function EmailDetailSkeleton() {
  return (
    <div className="px-6 py-5 space-y-5">
      <div className="space-y-2">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-3 w-1/3" />
      </div>
      <Skeleton className="h-10 w-full" />
      <div className="space-y-2">
        <Skeleton className="h-3 w-40" />
        <Skeleton className="h-24 w-full" />
      </div>
      <div className="space-y-2">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-28 w-full" />
      </div>
    </div>
  );
}
