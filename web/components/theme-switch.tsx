"use client";

import { ContrastIcon, MoonIcon, SunIcon } from "./icons";
import { THEMES, THEME_LABELS, useTheme, type Theme } from "./theme-provider";

const ICONS: Record<Theme, typeof SunIcon> = {
  light: SunIcon,
  dim: ContrastIcon,
  dark: MoonIcon,
};

/**
 * X exposes Default / Dim / Lights out as an explicit choice rather than a
 * binary toggle, so this is a radio group: every option is visible, the active
 * one is announced, and nothing depends on colour alone.
 */
export function ThemeSwitch({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="Display theme"
      className="flex w-fit flex-col items-center gap-1 rounded-full border border-line bg-raised p-1 xl:w-auto xl:flex-row"
    >
      {THEMES.map((option) => {
        const Icon = ICONS[option];
        const active = option === theme;
        return (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={THEME_LABELS[option]}
            title={THEME_LABELS[option]}
            onClick={() => setTheme(option)}
            className={`flex h-11 min-w-11 cursor-pointer items-center justify-center gap-2 rounded-full px-3 transition-colors duration-200 ${
              active
                ? "bg-brand text-white"
                : "text-muted hover:bg-hover hover:text-ink"
            }`}
          >
            <Icon className="h-[18px] w-[18px]" />
            {!compact && (
              <span className="hidden text-[13px] font-medium whitespace-nowrap xl:inline">
                {THEME_LABELS[option]}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
