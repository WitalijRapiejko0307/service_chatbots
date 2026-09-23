/** Reusable input component. */

import React from "react";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input: React.FC<InputProps> = ({
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
      <input
        className={`w-full px-3 py-2 border rounded-sm bg-surface transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-accent focus:border-accent ${
          error ? "border-danger focus:ring-danger" : "border-border"
        } ${className}`}
        {...props}
      />
      {error && <p className="mt-1 text-sm text-danger">{error}</p>}
      {!error && helperText && (
        <p className="mt-1 text-sm text-muted">{helperText}</p>
      )}
    </div>
  );
};



