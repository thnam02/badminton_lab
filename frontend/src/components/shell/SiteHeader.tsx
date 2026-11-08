"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { CONTAINER_CLASSES } from "./PageContainer";

const NAV = [
  { href: "/analyze", label: "Analyze", match: ["/analyze"] },
  { href: "/history", label: "History", match: ["/history", "/analysis"] },
  { href: "/compare", label: "Compare", match: ["/compare"] },
];

function isActive(pathname: string, prefixes: string[]): boolean {
  return prefixes.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function SiteHeader() {
  const pathname = usePathname() ?? "";
  const onAnalyze = isActive(pathname, ["/analyze"]);

  return (
    <header className="border-b border-border bg-bg">
      <div
        className={`${CONTAINER_CLASSES} flex flex-wrap items-center justify-between gap-4 py-4`}
      >
        <Link
          href="/"
          className="inline-flex min-h-11 items-center gap-2.5 rounded-lg text-text hover:text-text"
        >
          <LogoMark />
          <span className="font-display text-[19px] font-bold tracking-tight">
            Badminton Lab
          </span>
        </Link>
        <nav aria-label="Main" className="flex flex-wrap items-center gap-1">
          {NAV.map((item) => {
            const active = isActive(pathname, item.match);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`inline-flex min-h-11 items-center rounded-lg px-3.5 ${
                  active
                    ? "bg-surface-2 text-text hover:text-text"
                    : "text-text-muted hover:bg-surface-2 hover:text-text"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
          {!onAnalyze && (
            <Link
              href="/analyze"
              className="ml-2 hidden min-h-11 items-center sm:inline-flex gap-2 rounded-full bg-accent px-[18px] font-semibold text-bg hover:bg-accent-soft hover:text-bg"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              New analysis
            </Link>
          )}
        </nav>
      </div>
    </header>
  );
}

function LogoMark() {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 28 28"
      fill="none"
      aria-hidden="true"
      className="text-accent"
    >
      <circle cx="14" cy="21" r="4.5" stroke="currentColor" strokeWidth="2" />
      <path
        d="M10.5 18 6 5M14 16.5V4M17.5 18 22 5M8 11h12"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}
