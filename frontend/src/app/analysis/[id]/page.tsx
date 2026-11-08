import { AnalysisResultView } from "@/components/analysis/AnalysisResultView";
import { PageContainer } from "@/components/shell/PageContainer";

type Props = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ t?: string }>;
};

export default async function AnalysisPage({ params, searchParams }: Props) {
  const { id } = await params;
  const { t } = await searchParams;
  const seconds = t != null ? Number(t) : NaN;
  return (
    <PageContainer>
      <AnalysisResultView
        analysisId={id}
        initialTime={Number.isFinite(seconds) && seconds >= 0 ? seconds : undefined}
      />
    </PageContainer>
  );
}
