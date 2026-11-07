/** Shared class presets for the dark theme (see tailwind.config.ts tokens). */

export const buttonPrimary =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-full bg-accent px-6 font-semibold text-bg transition hover:bg-accent-soft hover:text-bg disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-accent";

export const buttonSecondary =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-full border border-border bg-surface px-[18px] text-text transition hover:border-accent hover:text-text disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-border";

export const buttonGhost =
  "inline-flex min-h-11 items-center gap-2 rounded-lg px-3 text-sm font-medium text-text-muted transition hover:bg-surface-2 hover:text-text";

export const eyebrow =
  "text-xs font-semibold uppercase tracking-[0.08em] text-text-muted";

export const cardTitle = "font-display text-[17px] font-semibold text-text";

export const pageTitle =
  "font-display text-4xl font-bold leading-[1.05] tracking-[-0.02em] text-text sm:text-[44px]";

export const chip =
  "inline-flex items-center rounded-full border border-border bg-surface-2 px-3 py-1 text-[13px] text-text";

export const inputBase =
  "block min-h-11 w-full rounded-xl border border-border bg-surface-2 px-3 text-text";

export const tile = "rounded-xl bg-surface-2 p-3.5";
