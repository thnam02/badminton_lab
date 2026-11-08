import { AnalysisResultView } from "@/components/analysis/AnalysisResultView";
import { PageContainer } from "@/components/shell/PageContainer";

type Props = {
  params: Promise<{ id: string }>;
};

export default async function AnalysisPage({ params }: Props) {
  const { id } = await params;
  return (
    <PageContainer>
      <AnalysisResultView analysisId={id} />
    </PageContainer>
  );
}
