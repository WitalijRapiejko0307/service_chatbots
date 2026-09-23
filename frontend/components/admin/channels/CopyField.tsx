"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Eye, EyeOff } from "lucide-react";
import { CopyButton } from "./CopyButton";

export function CopyField({ value, masked }: { value: string; masked?: boolean }) {
  const t = useTranslations("Channels");
  const [show, setShow] = useState(false);
  const display = masked && !show ? "•".repeat(Math.min(value.length, 24)) : value;
  return (
    <div className="flex items-center gap-2 mt-1.5">
      <code className="flex-1 min-w-0 bg-surface-hover border border-border rounded-sm px-3 py-1.5 text-xs font-mono text-foreground overflow-x-auto whitespace-nowrap block">
        {value ? display : <span className="text-muted">{t("notConfigured")}</span>}
      </code>
      {masked && value && (
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="text-muted hover:text-foreground"
          title={show ? t("hide") : t("show")}
        >
          {show ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      )}
      {value && <CopyButton value={value} />}
    </div>
  );
}
