"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Copy, Check } from "lucide-react";

export function CopyButton({ value, label }: { value: string; label?: string }) {
  const t = useTranslations("Channels");
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    if (!value) return;
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      type="button"
      onClick={handleCopy}
      disabled={!value}
      className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-sm border transition-colors
        border-[#BEBAB7] text-[#443C3C] hover:border-[#251D1C] hover:text-[#251D1C]
        disabled:opacity-40 disabled:cursor-not-allowed"
      title={label ?? t("copyToClipboard")}
    >
      {copied ? <Check size={12} className="text-green-600" /> : <Copy size={12} />}
      {copied ? t("copied") : t("copy")}
    </button>
  );
}
