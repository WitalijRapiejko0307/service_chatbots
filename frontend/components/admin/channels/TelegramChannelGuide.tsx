"use client";

import { useTranslations } from "next-intl";
import { CopyField } from "./CopyField";
import { ExtLink } from "./ExtLink";
import { richMarks } from "./richMarks";
import { Step } from "./Step";

export function TelegramChannelGuide({ telegramWebhook }: { telegramWebhook: string }) {
  const t = useTranslations("Channels");

  return (
    <div className="space-y-4">
      <div className="text-xs text-muted bg-surface-hover/60 rounded-sm p-3 space-y-1">
        <div className="font-semibold text-foreground mb-1.5">{t("needTitle")}</div>
        <div>• {t("telegram.needItem")}</div>
      </div>
      <div className="space-y-3">
        <Step n={1}>
          {t.rich("telegram.step1", {
            ...richMarks({
              botFather: (chunks) => (
                <ExtLink href="https://t.me/BotFather">{chunks}</ExtLink>
              ),
            }),
          })}
        </Step>
        <Step n={2}>{t("telegram.step2")}</Step>
        <Step n={3}>
          {t("telegram.step3")}
          {telegramWebhook ? <CopyField value={telegramWebhook} /> : (
            <p className="text-xs text-muted mt-1">{t("webhookAppearsAfterConnect")}</p>
          )}
        </Step>
      </div>
    </div>
  );
}
