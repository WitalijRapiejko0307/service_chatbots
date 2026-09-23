"use client";

import { useTranslations } from "next-intl";

export function AppUrlWarning() {
  const t = useTranslations("Channels");
  return (
    <div className="text-xs bg-warning/10 border border-warning/30 rounded-sm px-3 py-2 space-y-1">
      <div className="font-medium text-warning">{t("appUrlMissingTitle")}</div>
      <div className="text-warning">{t("appUrlMissingBody")}</div>
    </div>
  );
}
