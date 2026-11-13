import { LabellingWorkspace } from "@/components/labelling/LabellingWorkspace";
import { PageContainer } from "@/components/shell/PageContainer";

type Props = {
  params: Promise<{ datasetId: string }>;
  searchParams: Promise<{ video?: string }>;
};

export default async function CoachLabelPage({ params, searchParams }: Props) {
  const { datasetId } = await params;
  const video = Number((await searchParams).video);
  return (
    <PageContainer className="text-lg">
      <LabellingWorkspace
        batchId={datasetId}
        startPosition={Number.isInteger(video) && video > 0 ? video : undefined}
      />
    </PageContainer>
  );
}
