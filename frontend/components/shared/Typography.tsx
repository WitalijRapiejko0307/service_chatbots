/** Typography components for consistent text styling across the app. */

import React from "react";

interface TypographyProps {
  children: React.ReactNode;
  className?: string;
}

export const Heading1: React.FC<TypographyProps> = ({ children, className = "" }) => {
  return (
    <h1 className={`text-3xl font-bold leading-tight text-gray-900 ${className}`}>
      {children}
    </h1>
  );
};

export const Heading2: React.FC<TypographyProps> = ({ children, className = "" }) => {
  return (
    <h2 className={`text-2xl font-semibold leading-tight text-gray-900 ${className}`}>
      {children}
    </h2>
  );
};

export const Heading3: React.FC<TypographyProps> = ({ children, className = "" }) => {
  return (
    <h3 className={`text-xl font-semibold leading-normal text-gray-900 ${className}`}>
      {children}
    </h3>
  );
};

export const Heading4: React.FC<TypographyProps> = ({ children, className = "" }) => {
  return (
    <h4 className={`text-lg font-medium leading-normal text-gray-900 ${className}`}>
      {children}
    </h4>
  );
};

export const Body: React.FC<TypographyProps & { variant?: "default" | "muted" }> = ({
  children,
  variant = "default",
  className = "",
}) => {
  const colorClass = variant === "muted" ? "text-gray-600" : "text-gray-900";
  return (
    <p className={`text-base leading-normal ${colorClass} ${className}`}>
      {children}
    </p>
  );
};

export const Caption: React.FC<TypographyProps & { variant?: "default" | "muted" }> = ({
  children,
  variant = "default",
  className = "",
}) => {
  const colorClass = variant === "muted" ? "text-gray-500" : "text-gray-700";
  return (
    <p className={`text-xs leading-normal ${colorClass} ${className}`}>
      {children}
    </p>
  );
};

export const Small: React.FC<TypographyProps & { variant?: "default" | "muted" }> = ({
  children,
  variant = "default",
  className = "",
}) => {
  const colorClass = variant === "muted" ? "text-gray-500" : "text-gray-700";
  return (
    <span className={`text-sm leading-normal ${colorClass} ${className}`}>
      {children}
    </span>
  );
};
