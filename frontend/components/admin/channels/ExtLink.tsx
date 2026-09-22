import type React from "react";
import { ExternalLink } from "lucide-react";

export function ExtLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-[#251D1C] font-medium underline underline-offset-2 hover:opacity-70"
    >
      {children} <ExternalLink size={11} />
    </a>
  );
}
