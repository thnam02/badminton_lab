import { LoginForm } from "@/components/auth/LoginForm";
import { PageContainer } from "@/components/shell/PageContainer";

type Props = {
  searchParams: Promise<{ next?: string }>;
};

export default async function LoginPage({ searchParams }: Props) {
  const { next } = await searchParams;
  return (
    <PageContainer className="items-center pt-16">
      <LoginForm next={next} />
    </PageContainer>
  );
}
