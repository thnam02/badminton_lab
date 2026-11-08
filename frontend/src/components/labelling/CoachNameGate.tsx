"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Card";
import { COACH_NAME_KEY } from "@/lib/labelling";

type Props = {
  /** Rendered once a name is known; changeCoach forgets it and asks again. */
  children: (coach: string, changeCoach: () => void) => React.ReactNode;
};

/** Asks for the coach's name once and remembers it in this browser. */
export function CoachNameGate({ children }: Props) {
  const [coach, setCoach] = useState<string | null>(null);
  const [nameInput, setNameInput] = useState("");

  useEffect(() => {
    const saved = window.localStorage.getItem(COACH_NAME_KEY) ?? "";
    setCoach(saved.trim() ? saved : "");
    setNameInput(saved);
  }, []);

  if (coach === null) {
    return (
      <p className="text-text-muted" role="status">
        Loading…
      </p>
    );
  }

  if (!coach.trim()) {
    return (
      <Card className="flex max-w-xl flex-col gap-4">
        <h2 className="font-display text-2xl font-bold">Before you start</h2>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            const name = nameInput.trim();
            if (!name) return;
            window.localStorage.setItem(COACH_NAME_KEY, name);
            setCoach(name);
          }}
        >
          <label className="flex flex-col gap-2 text-lg font-semibold">
            Your name
            <input
              type="text"
              autoComplete="name"
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              className="min-h-14 rounded-[14px] border border-border bg-surface-2 px-4 text-lg font-normal text-text"
            />
          </label>
          <button
            type="submit"
            disabled={!nameInput.trim()}
            className="min-h-14 rounded-2xl bg-accent px-6 text-lg font-bold text-bg disabled:opacity-40"
          >
            Start reviewing
          </button>
        </form>
      </Card>
    );
  }

  return children(coach, () => {
    window.localStorage.removeItem(COACH_NAME_KEY);
    setCoach("");
  });
}
