import { languageName } from "@/lib/format";
import type { Toxicity } from "@/lib/types";

/**
 * Toxic and safe differ by colour, by word and by icon shape — colour alone
 * never carries the meaning.
 */
export function ToxicityBadge({ toxicity }: { toxicity: Toxicity }) {
  const { score, is_toxic, threshold } = toxicity;
  return (
    <span
      title={`Model probability ${score}% · flagged at ${threshold}% for this language`}
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px] font-bold tabular-nums ${
        is_toxic
          ? "bg-toxic-soft text-toxic"
          : "bg-safe-soft text-safe"
      }`}
    >
      <svg viewBox="0 0 16 16" aria-hidden="true" className="h-3.5 w-3.5" fill="currentColor">
        {is_toxic ? (
          <path d="M8 1l7 13H1L8 1zm-.75 5v4h1.5V6h-1.5zm0 5v1.5h1.5V11h-1.5z" />
        ) : (
          <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm3.5 5.2l-4.2 4.2-2.8-2.8 1.06-1.06 1.74 1.74 3.14-3.14L11.5 6.2z" />
        )}
      </svg>
      {score.toFixed(1)}% {is_toxic ? "Toxic" : "Safe"}
    </span>
  );
}

export function LanguageBadge({ code }: { code: string }) {
  if (!code || code === "und") return null;
  return (
    <span
      title={`Detected language: ${languageName(code)}`}
      className="inline-flex items-center rounded-full bg-brand-soft px-2.5 py-1 text-[12px] font-bold tracking-wide text-brand uppercase"
    >
      {code}
    </span>
  );
}

/** Horizontal meter used in the right rail; width encodes the score. */
export function ScoreMeter({
  value,
  tone = "brand",
  label,
}: {
  value: number;
  tone?: "brand" | "toxic" | "safe";
  label: string;
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const color =
    tone === "toxic" ? "bg-toxic" : tone === "safe" ? "bg-safe" : "bg-brand";
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-[13px] text-muted">{label}</span>
        <span className="text-[13px] font-bold tabular-nums">{clamped.toFixed(1)}%</span>
      </div>
      <div
        role="meter"
        aria-valuenow={Math.round(clamped)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
        className="h-1.5 w-full overflow-hidden rounded-full bg-hover"
      >
        <div
          className={`h-full rounded-full ${color} transition-[width] duration-300 ease-out`}
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
