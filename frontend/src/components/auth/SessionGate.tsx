"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchMe, type Me } from "@/lib/auth";

type Props = {
  children: (me: Me) => React.ReactNode;
};

/** Renders children with the signed-in user; sends anyone else to the login page. */
export function SessionGate({ children }: Props) {
  const router = useRouter();
  const pathname = usePathname() ?? "/";
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((user) => {
        if (cancelled) return;
        if (user) setMe(user);
        else router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      })
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : "Could not check sign-in"));
    return () => {
      cancelled = true;
    };
  }, [router, pathname]);

  if (error) {
    return (
      <p className="text-danger" role="alert">
        {error}
      </p>
    );
  }
  if (!me) {
    return (
      <p className="text-text-muted" role="status">
        Loading…
      </p>
    );
  }
  return <>{children(me)}</>;
}
