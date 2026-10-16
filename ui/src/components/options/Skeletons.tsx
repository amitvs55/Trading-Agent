// Placeholders shaped like the real content (same paddings, rows and wrapping), so nothing below
// them moves when the data lands.

const CHIP_WIDTHS = [150, 190, 250, 160, 300, 270];

export function SessionBarSkeleton() {
  return (
    <div className="flex gap-2 flex-wrap" aria-hidden>
      {CHIP_WIDTHS.map(w => <div key={w} className="skeleton h-[34px] rounded-lg max-w-full" style={{ width: w }} />)}
    </div>
  );
}

export function BoardSkeleton() {
  return (
    <section className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden" aria-hidden>
      <div className="px-5 py-4 border-b border-[#1e2d45] flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="skeleton h-2.5 w-16 rounded" />
          <div className="skeleton h-[30px] w-52 rounded mt-2" />
        </div>
        <div className="flex gap-1.5">{[88, 112, 132, 96].map(w => <div key={w} className="skeleton h-[26px] rounded-md" style={{ width: w }} />)}</div>
      </div>
      <div className="px-5 py-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 border-b border-[#1e2d45]">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i}>
            <div className="skeleton h-2.5 w-16 rounded" />
            <div className="skeleton h-4 w-20 rounded mt-1.5" />
            <div className="skeleton h-2.5 w-24 rounded mt-1.5" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_280px]">
        <div className="p-4">
          <div className="skeleton h-3 w-56 rounded mb-3" />
          <div className="grid grid-cols-1 sm:grid-cols-2 2xl:grid-cols-3 gap-2">
            {Array.from({ length: 12 }, (_, i) => <div key={i} className="skeleton h-[74px] rounded-lg" />)}
          </div>
        </div>
        <div className="p-4 border-t xl:border-t-0 xl:border-l border-[#1e2d45] flex flex-col gap-2">
          {Array.from({ length: 9 }, (_, i) => <div key={i} className="skeleton h-5 rounded" />)}
        </div>
      </div>
    </section>
  );
}

export function SignalCardSkeleton() {
  return (
    <div className="bg-surface border border-[#1e2d45] rounded-xl overflow-hidden" aria-hidden>
      <div className="h-0.5 bg-[#1e2d45]" />
      <div className="px-4 pt-3.5 pb-3">
        <div className="flex gap-2">{[64, 44, 56].map(w => <div key={w} className="skeleton h-5 rounded" style={{ width: w }} />)}</div>
        <div className="skeleton h-5 w-48 rounded mt-2" />
        <div className="skeleton h-3 w-64 max-w-full rounded mt-1.5" />
      </div>
      <div className="px-4 grid grid-cols-2 gap-x-3 gap-y-3">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i}>
            <div className="skeleton h-2.5 w-14 rounded" />
            <div className="skeleton h-5 w-24 rounded mt-1" />
            <div className="skeleton h-2.5 w-28 rounded mt-1" />
          </div>
        ))}
      </div>
      <div className="px-4 pt-6 pb-5"><div className="skeleton h-1.5 rounded-full" /></div>
      <div className="px-4 py-3 mt-1 border-t border-[#1e2d45] flex justify-between">
        <div className="skeleton h-3 w-56 rounded" /><div className="skeleton h-3 w-20 rounded" />
      </div>
    </div>
  );
}
