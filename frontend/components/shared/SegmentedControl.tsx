/** Two-or-more mutually exclusive choices in one bordered control (toolbar pattern). */

"use client";

import React from "react";

export interface SegmentedOption {
  value: string;
  label: string;
}

interface SegmentedControlProps {
  options: SegmentedOption[];
  value: string;
  onChange: (value: string) => void;
  /** Optional heading above the control */
  label?: string;
  size?: "sm" | "md";
  className?: string;
  /** Passed to the outer group (e.g. aria-label if label is absent) */
  "aria-label"?: string;
}

const sizeClasses = {
  sm: "px-3 py-1.5 text-sm",
  md: "px-4 py-2 text-sm",
};

export const SegmentedControl: React.FC<SegmentedControlProps> = ({
  options,
  value,
  onChange,
  label,
  size = "sm",
  className = "",
  "aria-label": ariaLabel,
}) => {
  const pad = sizeClasses[size];
  return (
    <div className={`w-full ${className}`}>
      {label ? (
        <span className="block text-sm font-medium text-foreground mb-1.5">{label}</span>
      ) : null}
      <div
        role="group"
        aria-label={ariaLabel ?? label}
        className="inline-flex w-full max-w-md rounded-sm border border-border bg-surface-hover/40 p-0.5 gap-0.5"
      >
        {options.map((opt) => {
          const active = opt.value === value;
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(opt.value)}
              className={`flex-1 min-w-0 rounded-sm font-medium transition-colors ${pad} ${
                active
                  ? "bg-accent text-accent-foreground shadow-sm"
                  : "bg-surface/90 text-foreground hover:bg-surface border border-transparent"
              }`}
            >
              <span className="block truncate">{opt.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};
