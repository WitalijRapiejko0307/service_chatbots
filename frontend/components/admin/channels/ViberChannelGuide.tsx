"use client";

import { useTranslations } from "next-intl";
import { AppUrlWarning } from "./AppUrlWarning";
import { CopyField } from "./CopyField";
import { ExtLink } from "./ExtLink";
import { richMarks } from "./richMarks";
import { Step } from "./Step";

export function ViberChannelGuide({
  viberWebhook,
  appBase,
}: {
  viberWebhook: string;
  appBase: string;
}) {
  const t = useTranslations("Channels");

  return (
    <div className="space-y-4">
      <div className="text-xs text-muted bg-surface-hover/60 rounded-sm p-3 space-y-1">
        <div className="font-semibold text-foreground mb-1.5">{t("needTitle")}</div>
        <div>• {t("viber.needItem1")}</div>
        <div>• {t("viber.needItem2")}</div>
        <div>• {t("viber.needItem3")}</div>
      </div>
      <p className="text-xs text-foreground bg-surface-hover/60 rounded-sm px-3 py-2">
        {t("viber.httpsNote")}
      </p>
      {!appBase && <AppUrlWarning />}
      <div className="space-y-3">
        <Step n={1}>
          {t.rich("viber.step1", {
            ...richMarks({
              adminPanel: (chunks) => (
                <ExtLink href="https://partners.viber.com">{chunks}</ExtLink>
              ),
            }),
          })}
        </Step>
        <Step n={2}>{t.rich("viber.step2", richMarks())}</Step>
        <Step n={3}>
          {t("viber.step3")}
          {viberWebhook ? (
            <CopyField value={viberWebhook} />
          ) : appBase ? (
            <p className="text-xs text-muted mt-1">{t("webhookAppearsAfterConnect")}</p>
          ) : (
            <AppUrlWarning />
          )}
        </Step>
      </div>
    </div>
  );
}
