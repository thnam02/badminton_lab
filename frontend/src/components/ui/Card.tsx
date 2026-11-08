type Props = React.HTMLAttributes<HTMLElement> & {
  as?: "section" | "div" | "article" | "aside";
};

export function Card({ as: Tag = "section", className = "", children, ...rest }: Props) {
  return (
    <Tag
      className={`rounded-card border border-border bg-surface p-6 ${className}`}
      {...rest}
    >
      {children}
    </Tag>
  );
}
