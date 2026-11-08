import { CoachNav } from "@/components/coach/CoachNav";
import { CoachRuleBuilder } from "@/components/coach/CoachRuleBuilder";
import { PageContainer } from "@/components/shell/PageContainer";
import { pageTitle } from "@/components/ui/styles";

export default function CoachRulesPage() {
  return (
    <PageContainer>
      <CoachNav />
      <header className="flex max-w-[820px] flex-col gap-2">
        <h1 className={pageTitle}>Teach the app what a good stroke looks like</h1>
        <p className="text-xl text-text-soft">
          Pick from pictures. No numbers needed. We then check your rule against the clips
          you reviewed.
        </p>
      </header>
      <CoachRuleBuilder />
    </PageContainer>
  );
}
