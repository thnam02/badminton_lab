import { CoachNav } from "@/components/coach/CoachNav";
import { RuleDraftList } from "@/components/coach/RuleDraftList";
import { PageContainer } from "@/components/shell/PageContainer";
import { pageTitle } from "@/components/ui/styles";

export default function RuleStudioPage() {
  return (
    <PageContainer>
      <CoachNav />
      <header className="flex max-w-[760px] flex-col gap-2">
        <h1 className={pageTitle}>Rule studio</h1>
        <p className="text-text-muted">
          Coach rules waiting for the team. Drafts never change players&apos; results: the
          dev team checks each one and promotes it into a rule version.
        </p>
      </header>
      <RuleDraftList />
    </PageContainer>
  );
}
