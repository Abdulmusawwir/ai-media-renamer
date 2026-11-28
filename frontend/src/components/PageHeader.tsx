import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface PageHeaderProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: ReactNode;
}

/** Consistent page identity: icon chip, title, description and optional action. */
export function PageHeader({ icon: Icon, title, description, action }: PageHeaderProps) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-start gap-3">
        <span className="ui-page-icon" aria-hidden="true">
          <Icon size={18} />
        </span>
        <div>
          <h2 className="text-lg font-semibold tracking-tight">{title}</h2>
          {description && <p className="text-sm text-text-dim">{description}</p>}
        </div>
      </div>
      {action && <div className="flex items-center gap-2">{action}</div>}
    </div>
  );
}
