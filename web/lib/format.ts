/** X's compact counts: 1234 -> 1.2K, 1500000 -> 1.5M. */
export function compactNumber(value: number): string {
  if (!Number.isFinite(value)) return "0";
  if (Math.abs(value) < 1000) return String(value);
  const units = [
    { limit: 1e9, suffix: "B" },
    { limit: 1e6, suffix: "M" },
    { limit: 1e3, suffix: "K" },
  ];
  for (const { limit, suffix } of units) {
    if (Math.abs(value) >= limit) {
      const scaled = value / limit;
      const digits = scaled < 100 ? 1 : 0;
      return `${scaled.toFixed(digits).replace(/\.0$/, "")}${suffix}`;
    }
  }
  return String(value);
}

/** "2h", "3d", "Mar 14" — the relative stamp X shows on each post. */
export function relativeTime(iso: string): string {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const seconds = Math.floor((Date.now() - then.getTime()) / 1000);
  if (seconds < 60) return `${Math.max(seconds, 1)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d`;
  const sameYear = then.getFullYear() === new Date().getFullYear();
  return then.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    ...(sameYear ? {} : { year: "numeric" }),
  });
}

export function absoluteTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

const LANGUAGE_NAMES = new Intl.DisplayNames(undefined, { type: "language" });

export function languageName(code: string): string {
  if (!code || code === "und") return "Unknown";
  try {
    return LANGUAGE_NAMES.of(code) ?? code.toUpperCase();
  } catch {
    return code.toUpperCase();
  }
}

/** Usernames arrive from URLs and forms: strip @, spaces and stray slashes. */
export function normalizeHandle(value: string): string {
  return value.trim().replace(/^@+/, "").replace(/[^\w]/g, "").slice(0, 15);
}
