/** Reusable slider component. */

import React from "react";

interface SliderProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: string;
  error?: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  showValue?: boolean;
}

export const Slider: React.FC<SliderProps> = ({
  label,
  error,
  value,
  min,
  max,
  step = 1,
  showValue = true,
  className = "",
  onChange,
  ...props
}) => {
  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-2">
        {label && (
          <label className="block text-sm font-medium text-foreground">
            {label}
          </label>
        )}
        {showValue && (
          <span className="text-sm font-medium text-foreground">{value}</span>
        )}
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={onChange}
        className={`w-full h-2 bg-border rounded-sm appearance-none cursor-pointer accent-accent ${
          error ? "border-danger" : ""
        } ${className}`}
        style={{
          background: `linear-gradient(to right, var(--accent) 0%, var(--accent) ${((value - min) / (max - min)) * 100}%, var(--border) ${((value - min) / (max - min)) * 100}%, var(--border) 100%)`,
        }}
        {...props}
      />
      {error && <p className="mt-1 text-sm text-danger">{error}</p>}
    </div>
  );
};






