"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/coach/rules", label: "My rules" },
  { href: "/coach/studio", label: "Rule studio" },
];

export function CoachNav() {
  const pathname = usePathname() ?? "";
  return (
    <nav aria-label="Coach workspace" className="flex flex-wrap items-center gap-2">
      <span className="rounded-md bg-warn px-2 py-1 text-xs font-semibold uppercase tracking-[0.06em] text-bg">
        Coach workspace
      </span>
      {LINKS.map((link) => {
        const active = pathname === link.href;
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={active ? "page" : undefined}
            className={`inline-flex min-h-11 items-center rounded-lg px-3.5 ${
              active
                ? "bg-surface-2 text-text hover:text-text"
                : "text-text-muted hover:bg-surface-2 hover:text-text"
            }`}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
