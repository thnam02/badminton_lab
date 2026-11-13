import { SignedInBar } from "@/components/auth/SignedInBar";

export default function CoachLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SignedInBar area="Coach workspace" />
      {children}
    </>
  );
}
