import type React from "react";

export function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="flex-shrink-0 w-6 h-6 rounded-full bg-[#EEEAE7] text-[#443C3C] text-xs font-bold flex items-center justify-center mt-0.5">
        {n}
      </span>
      <div className="flex-1 min-w-0 text-sm text-[#443C3C] leading-relaxed break-words">{children}</div>
    </div>
  );
}
