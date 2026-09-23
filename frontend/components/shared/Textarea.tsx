/** Reusable textarea component. */

import React from "react";

interface TextareaProps
  extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Textarea: React.FC<TextareaProps> = ({
  label,
  error,
  helperText,
  className = "",
  ...props
}) => {
  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-foreground mb-1">
          {label}
        </label>
      )}
      <textarea
        className={`w-full px-3 py-2 border rounded-sm bg-surface transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent ${
          error ? "border-danger focus:ring-danger" : "border-border"
        } ${className}`}
        {...props}
      />
      {helperText && !error && (
        <p className="mt-1 text-xs text-muted">{helperText}</p>
      )}
      {error && <p className="mt-1 text-sm text-danger">{error}</p>}
    </div>
  );
};


