import type { ReactNode } from "react";

type Props = {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
};

export function SectionCard({ title, description, action, children }: Props) {
  return (
    <div className="card">
      <div className="page-header mb-2.5">
        <div>
          <h3 className="title m-0 text-lg">{title}</h3>
          {description && <div className="muted">{description}</div>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}
