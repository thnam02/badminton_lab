import Link from "next/link";
import { PageContainer } from "@/components/shell/PageContainer";
import {
  buttonPrimary,
  buttonSecondary,
  eyebrow,
  pageTitle,
} from "@/components/ui/styles";

const FEATURES = [
  "Interactive stroke timeline tied to your video",
  "Reference-group comparison — not a fake technique score",
  "Coaching that cites measurements you can verify",
];

export default function HomePage() {
  return (
    <PageContainer className="min-h-[70vh] justify-center gap-10">
      <div className="flex max-w-2xl flex-col gap-5">
        <p className={eyebrow}>Badminton technique analysis</p>
        <h1 className={pageTitle}>Badminton Lab</h1>
        <p className="text-[17px] leading-relaxed text-text-muted">
          Upload a forehand smash or clear, see stroke phases and contact, review
          evidence-backed findings against a reference group, and get one clear
          coaching focus for your next session.
        </p>
        <div className="flex flex-wrap gap-3 pt-2">
          <Link href="/analyze" className={buttonPrimary}>
            Analyze a stroke
          </Link>
          <Link href="/history" className={buttonSecondary}>
            View history
          </Link>
        </div>
      </div>

      <ul className="grid gap-4 text-text-soft sm:grid-cols-3">
        {FEATURES.map((text) => (
          <li key={text} className="rounded-card border border-border bg-surface p-5">
            {text}
          </li>
        ))}
      </ul>
    </PageContainer>
  );
}
