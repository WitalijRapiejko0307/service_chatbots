/** Generic badge component for displaying status indicators. */

import React from "react";

export type BadgeVariant = "default" | "success" | "warning" | "error" | "info";

interface BadgeProps {
  variant?: BadgeVariant;
  size?: "sm" | "md" | "lg";
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  default: "bg-surface-hover text-foreground border-border",
  success: "bg-success/15 text-success border-success/30",
  warning: "bg-warning/20 text-warning border-warning/30",
  error: "bg-danger/15 text-danger border-danger/30",
  info: "bg-accent/20 text-accent border-accent/30",
};

const sizeClasses = {
  sm: "px-2 py-0.5 text-xs",
  md: "px-2 py-1 text-xs",
  lg: "px-3 py-1.5 text-sm",
};

export const Badge: React.FC<BadgeProps> = ({
  variant = "default",
  size = "md",
  children,
  className = "",
}) => {
  return (
    <span
      className={`inline-flex items-center leading-5 font-semibold rounded-sm border ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
    >
      {children}
    </span>
  );
};
