"use client";

import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import type { ChannelConfig } from "@/lib/types/channel";
import { AppUrlWarning } from "./AppUrlWarning";
import { CopyField } from "./CopyField";
import { ExtLink } from "./ExtLink";
import { InlineTokenSetup } from "./InlineTokenSetup";
import { richMarks } from "./richMarks";
import { Step } from "./Step";

export function InstagramChannelGuide({
  igWebhookUrl,
  config,
  onConfigUpdate,
}: {
  igWebhookUrl: string;
  config: ChannelConfig | null;
  onConfigUpdate: (config: ChannelConfig) => void;
}) {
  const t = useTranslations("Channels");

  return (
    <div className="space-y-4">
      <div className="text-xs text-[#9A9590] bg-[#EEEAE7]/60 rounded-sm p-3 space-y-1">
        <div className="font-semibold text-[#443C3C] mb-1.5">{t("needTitle")}</div>
        <div>• {t("instagram.needItem1")}</div>
        <div>• {t("instagram.needItem2")}</div>
        <div>• {t("instagram.needItem3")}</div>
      </div>
      <p className="text-xs text-[#9A9590]">{t("instagram.intro")}</p>
      <div className="text-xs text-[#443C3C] bg-[#EEEAE7]/60 rounded-sm px-3 py-2">
        {t("instagram.appReviewNote")}
      </div>
      <div className="space-y-3">
        <Step n={1}>
          {t.rich("instagram.step1", {
            ...richMarks({
              metaDev: (chunks) => (
                <ExtLink href="https://developers.facebook.com/apps">{chunks}</ExtLink>
              ),
            }),
          })}
        </Step>
        <Step n={2}>{t.rich("instagram.step2", richMarks())}</Step>
        <Step n={3}>
          <div className="font-medium">{t("instagram.step3Title")}</div>
          <div className="text-xs text-[#9A9590] mt-0.5 mb-2">{t("instagram.step3Help")}</div>
          <div className="space-y-1 mb-3">
            <div className="text-xs font-medium text-[#443C3C]">
              {t("instagram.callbackUrl")}{" "}
              <span className="font-normal text-[#9A9590]">{t("instagram.callbackUrlHint")}</span>
            </div>
            {igWebhookUrl ? <CopyField value={igWebhookUrl} /> : <AppUrlWarning />}
          </div>
          <div className="space-y-1">
            <div className="text-xs font-medium text-[#443C3C]">
              {t("instagram.verifyTokenLabel")}{" "}
              <span className="font-normal text-[#9A9590]">
                {t("instagram.verifyTokenHintLabel")}
              </span>
            </div>
            {config?.instagram_verify_token ? (
              <>
                <CopyField value={config.instagram_verify_token} masked />
                <div className="text-xs text-[#9A9590]">{t("instagram.verifyTokenSameValue")}</div>
              </>
            ) : (
              <InlineTokenSetup
                channel="instagram"
                onSave={async (token) => {
                  await api.updateInstagramSettings({ verify_token: token });
                  const updated = await api.getChannelConfig();
                  onConfigUpdate(updated);
                }}
              />
            )}
          </div>
          <div className="text-xs text-[#9A9590] mt-3 bg-[#EEEAE7]/60 rounded-sm px-3 py-2">
            {t.rich("instagram.verifyAfterSave", richMarks())}
          </div>
        </Step>
        <Step n={4}>{t.rich("instagram.step4", richMarks())}</Step>
        <Step n={5}>{t("instagram.step5")}</Step>
        <p className="text-xs text-[#9A9590]">{t("instagram.oauthPathNote")}</p>
        <p className="text-xs text-[#9A9590]">{t("instagram.tokenExpiryNote")}</p>
      </div>
    </div>
  );
}
