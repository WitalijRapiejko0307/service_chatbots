"use client";

import { useTranslations } from "next-intl";
import type { ChannelBinding } from "@/lib/types/channel";
import { ChannelCard } from "./ChannelCard";
import { TelegramChannelGuide } from "./TelegramChannelGuide";

interface TelegramChannelSectionProps {
  agentId: string;
  bindings: ChannelBinding[];
  telegramWebhook: string;
  webhookFor: (binding?: ChannelBinding) => string;
  onBindingsChange: () => void;
}

export function TelegramChannelSection({
  agentId,
  bindings,
  telegramWebhook,
  webhookFor,
  onBindingsChange,
}: TelegramChannelSectionProps) {
  const t = useTranslations("Channels");

  return (
    <ChannelCard
      title={t("telegram.title")}
      icon="✈️"
      bindings={bindings}
      agentId={agentId}
      channelType="telegram"
      webhookFor={webhookFor}
      onBindingsChange={onBindingsChange}
      guide={<TelegramChannelGuide telegramWebhook={telegramWebhook} />}
    />
  );
}
