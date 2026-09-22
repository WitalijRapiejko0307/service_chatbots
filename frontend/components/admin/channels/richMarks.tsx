import React from "react";

export function richMarks(extra?: Record<string, (chunks: React.ReactNode) => React.ReactNode>) {
  return {
    strong: (chunks: React.ReactNode) => <strong>{chunks}</strong>,
    em: (chunks: React.ReactNode) => <em>{chunks}</em>,
    code: (chunks: React.ReactNode) => (
      <code className="bg-[#EEEAE7] px-1 rounded-sm text-xs">{chunks}</code>
    ),
    ...extra,
  };
}
