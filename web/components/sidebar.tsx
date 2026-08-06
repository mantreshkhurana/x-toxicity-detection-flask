"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ChartIcon,
  HomeIcon,
  LanguagesIcon,
  SearchIcon,
  ShieldIcon,
  XLogo,
} from "./icons";
import { ThemeSwitch } from "./theme-switch";

const NAV = [
  { href: "/", label: "Home", icon: HomeIcon },
  { href: "/analyze", label: "Analyze text", icon: LanguagesIcon },
  { href: "/model", label: "Model", icon: ChartIcon },
] as const;

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

/**
 * X's left rail: icon-only at md, icons + labels from xl up, always the same
 * order and position so the app never moves its navigation between pages.
 */
export function Sidebar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 hidden h-dvh shrink-0 flex-col items-end px-2 md:flex xl:w-[275px]">
      <div className="flex h-full w-[72px] flex-col xl:w-full">
        <Link
          href="/"
          aria-label="X Toxicity Detection home"
          className="mt-1 flex h-[52px] w-[52px] cursor-pointer items-center justify-center rounded-full transition-colors duration-200 hover:bg-hover"
        >
          <XLogo className="h-7 w-7" />
        </Link>

        <nav aria-label="Primary" className="mt-1 flex flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = isActive(pathname, href);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className="group flex cursor-pointer items-center gap-4 self-start rounded-full py-2 pr-5 pl-3 transition-colors duration-200 hover:bg-hover"
              >
                <Icon filled={active} className="h-[26px] w-[26px]" />
                <span
                  className={`hidden text-xl xl:inline ${
                    active ? "font-bold" : "font-normal"
                  }`}
                >
                  {label}
                </span>
              </Link>
            );
          })}
        </nav>

        <Link
          href="/"
          className="mt-4 flex h-[52px] w-[52px] cursor-pointer items-center justify-center rounded-full bg-brand text-white transition-colors duration-200 hover:bg-brand-hover xl:h-auto xl:w-[90%] xl:py-3"
        >
          <SearchIcon className="h-6 w-6 xl:hidden" />
          <span className="hidden text-[17px] font-bold xl:inline">
            Analyze a profile
          </span>
        </Link>

        <div className="mt-auto mb-4 flex flex-col gap-3">
          <div className="hidden items-center gap-2 rounded-full px-3 py-2 text-[13px] text-muted xl:flex">
            <ShieldIcon className="h-4 w-4" />
            <span>Scores are a signal, not a verdict</span>
          </div>
          <ThemeSwitch />
        </div>
      </div>
    </header>
  );
}

/** Bottom navigation for phones: 4 destinations, labelled, 44px+ targets. */
export function MobileNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-40 flex items-stretch border-t border-line bg-canvas/95 backdrop-blur-md pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = isActive(pathname, href);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`flex flex-1 cursor-pointer flex-col items-center gap-0.5 py-2.5 text-[11px] transition-colors duration-200 ${
              active ? "text-brand" : "text-muted"
            }`}
          >
            <Icon filled={active} className="h-6 w-6" />
            <span className={active ? "font-semibold" : ""}>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
