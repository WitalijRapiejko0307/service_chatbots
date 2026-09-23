"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/shared/Button";

export function InlineTokenSetup({
  channel,
  onSave,
}: {
  channel: "instagram";
  onSave: (token: string) => Promise<void>;
}) {
  const t = useTranslations("Channels");
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setSaving(true);
    try {
      await onSave(trimmed);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-2 p-3 bg-surface-hover/50 border border-border rounded-sm space-y-2">
      <p className="text-xs text-foreground">{t("inlineTokenIntro")}</p>
      <div className="flex gap-2">
        <input
          className="flex-1 text-sm px-2.5 py-1.5 border border-border rounded-sm outline-none focus:border-border-strong bg-surface"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={t("inlineTokenPlaceholder", { channel })}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
        />
        <Button type="button" size="sm" onClick={handleSave} disabled={!value.trim() || saving}>
          {saving ? t("saving") : saved ? t("savedCheck") : t("save")}
        </Button>
      </div>
    </div>
  );
}
