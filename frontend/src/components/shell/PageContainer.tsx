type Props = {
  children: React.ReactNode;
  className?: string;
};

export const CONTAINER_CLASSES = "mx-auto w-full max-w-page px-6";

/** Page body: 1280px max width, 24px gutter, vertical rhythm shared by every page. */
export function PageContainer({ children, className = "" }: Props) {
  return (
    <main
      id="main"
      className={`${CONTAINER_CLASSES} flex flex-col gap-7 pb-16 pt-8 sm:pt-10 ${className}`}
    >
      {children}
    </main>
  );
}
