import { AdminDataset } from "@/components/admin/AdminDataset";
import { PageContainer } from "@/components/shell/PageContainer";

type Props = {
  params: Promise<{ datasetId: string }>;
};

export default async function AdminDatasetPage({ params }: Props) {
  const { datasetId } = await params;
  return (
    <PageContainer>
      <AdminDataset datasetId={datasetId} />
    </PageContainer>
  );
}
