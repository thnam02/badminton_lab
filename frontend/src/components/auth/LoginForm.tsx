"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { buttonPrimary, inputBase, pageTitle } from "@/components/ui/styles";
import { login } from "@/lib/auth";
import { homeFor } from "@/lib/session";

type Props = { next?: string };

/** Only follow in-app paths for the role that signed in. */
export function destinationAfterLogin(role: "admin" | "coach", next?: string): string {
  const home = homeFor(role);
  if (next && next.startsWith(home) && !next.startsWith("//")) return next;
  return home;
}

export function LoginForm({ next }: Props) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      const me = await login(password);
      router.replace(destinationAfterLogin(me.role, next));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not sign in");
      setBusy(false);
    }
  }

  return (
    <Card className="mx-auto flex w-full max-w-md flex-col gap-5">
      <h1 className={pageTitle}>Sign in</h1>
      <p className="text-text-muted">For the coach workspace and the admin area.</p>
      <form
        className="flex flex-col gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (password && !busy) void submit();
        }}
      >
        <label className="flex flex-col gap-2 font-semibold">
          Password
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={`${inputBase} min-h-12 font-normal`}
          />
        </label>
        <button type="submit" disabled={!password || busy} className={`${buttonPrimary} min-h-12`}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        {error && (
          <p className="text-danger" role="alert">
            {error}
          </p>
        )}
      </form>
    </Card>
  );
}
