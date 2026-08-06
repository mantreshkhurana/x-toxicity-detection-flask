import { languageName } from "@/lib/format";
import type { Summary } from "@/lib/types";

const SIZE = 168;
const STROKE = 20;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * Two-slice donut drawn as SVG — no chart library, no client JS.
 *
 * The ring is decorative: the same numbers are in the centre label and in the
 * legend below it, so the split is readable with colour vision differences,
 * with a screen reader, and before any CSS loads.
 */
export function ToxicityDonut({ summary }: { summary: Summary }) {
  const ratio = Math.max(0, Math.min(100, summary.toxic_ratio));
  const toxicArc = (ratio / 100) * CIRCUMFERENCE;

  return (
    <figure className="flex flex-col items-center">
      <div className="relative">
        <svg
          width={SIZE}
          height={SIZE}
          viewBox={`0 0 ${SIZE} ${SIZE}`}
          role="img"
          aria-label={`${summary.toxic} of ${summary.total} posts flagged toxic, ${ratio}% of the timeline`}
          className="-rotate-90"
        >
          <circle
            cx={SIZE / 2}
            cy={SIZE / 2}
            r={RADIUS}
            fill="none"
            stroke="var(--safe)"
            strokeWidth={STROKE}
          />
          {ratio > 0 && (
            <circle
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={RADIUS}
              fill="none"
              stroke="var(--toxic)"
              strokeWidth={STROKE}
              strokeDasharray={`${toxicArc} ${CIRCUMFERENCE - toxicArc}`}
              strokeLinecap={ratio >= 100 ? "butt" : "round"}
            />
          )}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[28px] leading-none font-bold tabular-nums">
            {ratio.toFixed(0)}%
          </span>
          <span className="mt-1 text-[12px] text-muted">toxic</span>
        </div>
      </div>

      <figcaption className="mt-4 flex w-full items-center justify-center gap-6">
        <LegendItem color="var(--safe)" label="Safe" value={summary.safe} />
        <LegendItem color="var(--toxic)" label="Toxic" value={summary.toxic} />
      </figcaption>
    </figure>
  );
}

function LegendItem({
  color,
  label,
  value,
}: {
  color: string;
  label: string;
  value: number;
}) {
  return (
    <span className="flex items-center gap-2">
      <span
        aria-hidden="true"
        className="h-2.5 w-2.5 rounded-full"
        style={{ background: color }}
      />
      <span className="text-[13px] text-muted">{label}</span>
      <span className="text-[15px] font-bold tabular-nums">{value}</span>
    </span>
  );
}

/** Language mix of the analyzed timeline, most frequent first. */
export function LanguageBreakdown({ summary }: { summary: Summary }) {
  const entries = Object.entries(summary.languages).filter(
    ([code]) => code !== "und",
  );
  if (entries.length === 0) return null;

  return (
    <ul className="flex flex-col gap-2.5">
      {entries.slice(0, 6).map(([code, count]) => {
        const share = (count / summary.total) * 100;
        return (
          <li key={code}>
            <div className="mb-1 flex items-baseline justify-between gap-2">
              <span className="truncate text-[13px]">{languageName(code)}</span>
              <span className="text-[13px] text-muted tabular-nums">
                {count} {count === 1 ? "post" : "posts"}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-hover">
              <div
                className="h-full rounded-full bg-brand"
                style={{ width: `${Math.max(share, 3)}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
