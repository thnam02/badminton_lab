"use client";

import { useEffect, useState } from "react";
import { CONTAINER_CLASSES } from "@/components/shell/PageContainer";
import { fetchMe, logout, type Me } from "@/lib/auth";
import { loadPage } from "@/lib/navigation";

/** Thin bar above the coach / admin pages: who is signed in, and sign out. */
export function SignedInBar({ area }: { area: "Coach workspace" | "Admin" }) {
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    fetchMe().then(setMe).catch(() => setMe(null));
  }, []);

  return (
    <div className="border-b border-border bg-surface">
      <div className={`${CONTAINER_CLASSES} flex flex-wrap items-center justify-between gap-3 py-1.5`}>
        <span className="rounded-md bg-warn px-2 py-1 text-xs font-semibold uppercase tracking-[0.06em] text-bg">
          {area}
        </span>
        <span className="flex items-center gap-3 text-sm text-text-muted">
          {me && <>Signed in as {me.name}</>}
          <button
            type="button"
            onClick={async () => {
              await logout();
              loadPage("/login");
            }}
            className="inline-flex min-h-11 items-center rounded-lg px-3 text-text hover:bg-surface-2"
          >
            Sign out
          </button>
        </span>
      </div>
    </div>
  );
}
