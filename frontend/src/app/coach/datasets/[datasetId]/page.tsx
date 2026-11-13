import { CoachDataset } from "@/components/labelling/CoachDataset";
import { PageContainer } from "@/components/shell/PageContainer";

type Props = {
  params: Promise<{ datasetId: string }>;
};

export default async function CoachDatasetPage({ params }: Props) {
  const { datasetId } = await params;
  return (
    <PageContainer>
      <CoachDataset datasetId={datasetId} />
    </PageContainer>
  );
}
