import { SignedInBar } from "@/components/auth/SignedInBar";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <SignedInBar area="Admin" />
      {children}
    </>
  );
}
