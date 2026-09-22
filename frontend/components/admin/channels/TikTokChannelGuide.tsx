"use client";

import { useTranslations } from "next-intl";
import { CopyField } from "./CopyField";
import { ExtLink } from "./ExtLink";
import { richMarks } from "./richMarks";
import { Step } from "./Step";

export function TikTokChannelGuide({
  tiktokWebhook,
  tiktokPendingAccess,
}: {
  tiktokWebhook: string;
  tiktokPendingAccess: boolean;
}) {
  const t = useTranslations("Channels");

  return (
    <div className="space-y-4">
      <div className="text-xs text-[#9A9590] bg-[#EEEAE7]/60 rounded-sm p-3 space-y-1">
        <div className="font-semibold text-[#443C3C] mb-1.5">{t("needTitle")}</div>
        <div>• {t("tiktok.needItem1")}</div>
        <div>• {t("tiktok.needItem2")}</div>
        <div>• {t("tiktok.needItem3")}</div>
      </div>
      <p className="text-xs text-[#9A9590]">
        {tiktokPendingAccess ? t("tiktok.introPending") : t("tiktok.introEnabled")}
      </p>
      <div className="space-y-3">
        <Step n={1}>
          {t.rich("tiktok.step1", {
            ...richMarks({
              docs: (chunks) => (
                <ExtLink href="https://developers.tiktok.com/doc/app-review-guidelines">
                  {chunks}
                </ExtLink>
              ),
            }),
          })}
        </Step>
        <Step n={2}>{t("tiktok.step2")}</Step>
        <Step n={3}>
          {t("tiktok.step3")}
          {tiktokWebhook ? (
            <CopyField value={tiktokWebhook} />
          ) : (
            <p className="text-xs text-[#9A9590] mt-1">{t("webhookAppearsAfterConnect")}</p>
          )}
        </Step>
      </div>
    </div>
  );
}
