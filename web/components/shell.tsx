import Link from "next/link";
import type { ReactNode } from "react";
import { BackIcon } from "./icons";

/**
 * X's three-column frame: nav rail, a 600px centre column that owns the
 * scroll, and a right rail that appears only when there is room for it.
 */
export function Columns({
  children,
  rail,
}: {
  children: ReactNode;
  rail?: ReactNode;
}) {
  return (
    <>
      <main className="w-full min-w-0 max-w-[600px] border-x border-line pb-20 md:pb-0">
        {children}
      </main>
      {rail && (
        <aside className="sticky top-0 hidden h-dvh w-[350px] shrink-0 overflow-y-auto px-8 py-3 lg:block">
          <div className="flex flex-col gap-4">{rail}</div>
        </aside>
      )}
    </>
  );
}

/**
 * Sticky column header. Blurred translucent bar, optional back button that
 * returns to a real URL rather than depending on history depth.
 */
export function ColumnHeader({
  title,
  subtitle,
  backHref,
}: {
  title: string;
  subtitle?: string;
  backHref?: string;
}) {
  return (
    <div className="sticky top-0 z-30 flex items-center gap-6 border-b border-line bg-canvas/85 px-4 py-2 backdrop-blur-md">
      {backHref && (
        <Link
          href={backHref}
          aria-label="Back"
          className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full transition-colors duration-200 hover:bg-hover"
        >
          <BackIcon />
        </Link>
      )}
      <div className="min-w-0">
        <h1 className="truncate text-[20px] leading-6 font-extrabold">{title}</h1>
        {subtitle && (
          <p className="truncate text-[13px] text-muted">{subtitle}</p>
        )}
      </div>
    </div>
  );
}

export function RailCard({
  title,
  children,
  footer,
}: {
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-2xl bg-raised">
      <h2 className="px-4 pt-3 pb-2 text-xl font-extrabold">{title}</h2>
      <div className="px-4 pb-4">{children}</div>
      {footer}
    </section>
  );
}

export function RailFooter() {
  return (
    <nav
      aria-label="About"
      className="flex flex-wrap gap-x-3 gap-y-1 px-4 pb-8 text-[13px] text-muted"
    >
      <Link href="/model" className="cursor-pointer hover:underline">
        Model card
      </Link>
      <Link href="/analyze" className="cursor-pointer hover:underline">
        Analyze text
      </Link>
      <a
        href="https://github.com/mantreshkhurana/x-toxicity-detection-flask"
        target="_blank"
        rel="noopener noreferrer"
        className="cursor-pointer hover:underline"
      >
        Source
      </a>
      <span>© {new Date().getFullYear()} Mantresh Khurana</span>
    </nav>
  );
}
