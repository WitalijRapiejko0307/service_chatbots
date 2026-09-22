"use client";

import { useTranslations } from "next-intl";

export function AppUrlWarning() {
  const t = useTranslations("Channels");
  return (
    <div className="text-xs bg-amber-50 border border-amber-200 rounded-sm px-3 py-2 space-y-1">
      <div className="font-medium text-amber-800">{t("appUrlMissingTitle")}</div>
      <div className="text-amber-700">{t("appUrlMissingBody")}</div>
    </div>
  );
}
