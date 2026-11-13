import { LabelView } from "@/components/admin/LabelView";
import { PageContainer } from "@/components/shell/PageContainer";

type Props = {
  params: Promise<{ datasetId: string; analysisId: string }>;
};

export default async function AdminLabelPage({ params }: Props) {
  const { datasetId, analysisId } = await params;
  return (
    <PageContainer>
      <LabelView datasetId={datasetId} analysisId={analysisId} />
    </PageContainer>
  );
}
