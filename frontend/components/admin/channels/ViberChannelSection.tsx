"use client";

import { useTranslations } from "next-intl";
import type { ChannelBinding } from "@/lib/types/channel";
import { ChannelCard } from "./ChannelCard";
import { ViberChannelGuide } from "./ViberChannelGuide";

interface ViberChannelSectionProps {
  agentId: string;
  bindings: ChannelBinding[];
  viberWebhook: string;
  appBase: string;
  webhookFor: (binding?: ChannelBinding) => string;
  onBindingsChange: () => void;
}

export function ViberChannelSection({
  agentId,
  bindings,
  viberWebhook,
  appBase,
  webhookFor,
  onBindingsChange,
}: ViberChannelSectionProps) {
  const t = useTranslations("Channels");

  return (
    <ChannelCard
      title={t("viber.title")}
      icon="💜"
      bindings={bindings}
      agentId={agentId}
      channelType="viber"
      webhookFor={webhookFor}
      onBindingsChange={onBindingsChange}
      guide={<ViberChannelGuide viberWebhook={viberWebhook} appBase={appBase} />}
    />
  );
}
