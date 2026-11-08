import { LabellingWorkspace } from "@/components/labelling/LabellingWorkspace";
import { PageContainer } from "@/components/shell/PageContainer";

type Props = {
  params: Promise<{ batchId: string }>;
};

export default async function CoachBatchPage({ params }: Props) {
  const { batchId } = await params;
  return (
    <PageContainer className="text-lg">
      <LabellingWorkspace batchId={batchId} />
    </PageContainer>
  );
}
