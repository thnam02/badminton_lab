import { redirect } from "next/navigation";

type Props = {
  params: Promise<{ batchId: string }>;
};

/** Older links went straight to a batch's labelling screen. */
export default async function OldBatchPage({ params }: Props) {
  const { batchId } = await params;
  redirect(`/coach/datasets/${encodeURIComponent(batchId)}/label`);
}
