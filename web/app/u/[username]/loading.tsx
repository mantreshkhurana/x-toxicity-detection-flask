import { Columns, ColumnHeader } from "@/components/shell";

/**
 * Skeleton mirrors the real layout's dimensions so nothing shifts when the
 * data lands (CLS stays flat), and it appears instead of a blocking spinner.
 */
export default function LoadingProfile() {
  return (
    <Columns
      rail={
        <div className="rounded-2xl bg-raised p-4">
          <div className="skeleton mx-auto h-[168px] w-[168px] rounded-full" />
          <div className="skeleton mt-5 h-3 w-full rounded-full" />
          <div className="skeleton mt-3 h-3 w-2/3 rounded-full" />
        </div>
      }
    >
      <ColumnHeader title="Analyzing…" backHref="/" />

      <div aria-hidden="true">
        <div className="skeleton h-[140px] w-full" />
        <div className="px-4 pb-3">
          <div className="skeleton -mt-14 h-[112px] w-[112px] rounded-full border-4 border-canvas" />
          <div className="skeleton mt-3 h-5 w-40 rounded-full" />
          <div className="skeleton mt-2 h-4 w-24 rounded-full" />
          <div className="skeleton mt-4 h-4 w-64 rounded-full" />
        </div>
        <div className="flex border-y border-line">
          {[0, 1, 2].map((index) => (
            <div key={index} className="flex-1 px-4 py-4">
              <div className="skeleton mx-auto h-4 w-16 rounded-full" />
            </div>
          ))}
        </div>
        {[0, 1, 2, 3, 4].map((index) => (
          <div key={index} className="flex gap-3 border-b border-line px-4 py-3">
            <div className="skeleton h-12 w-12 shrink-0 rounded-full" />
            <div className="flex-1">
              <div className="skeleton h-4 w-44 rounded-full" />
              <div className="skeleton mt-2 h-4 w-full rounded-full" />
              <div className="skeleton mt-2 h-4 w-4/5 rounded-full" />
              <div className="skeleton mt-3 h-6 w-28 rounded-full" />
            </div>
          </div>
        ))}
      </div>

      <p role="status" aria-live="polite" className="sr-only">
        Fetching posts and scoring them for toxicity.
      </p>
    </Columns>
  );
}
