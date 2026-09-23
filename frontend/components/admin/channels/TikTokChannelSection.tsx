"use client";

import { useTranslations } from "next-intl";
import { isPendingChannelAccess } from "@/lib/utils/channelDisplay";
import type { ChannelBinding } from "@/lib/types/channel";
import { ChannelCard } from "./ChannelCard";
import { TikTokChannelGuide } from "./TikTokChannelGuide";

interface TikTokChannelSectionProps {
  agentId: string;
  bindings: ChannelBinding[];
  tiktokWebhook: string;
  tiktokPendingAccess: boolean;
  tiktokMessagingEnabled: boolean;
  oauthAvailable: boolean;
  webhookFor: (binding?: ChannelBinding) => string;
  onBindingsChange: () => void;
}

export function TikTokChannelSection({
  agentId,
  bindings,
  tiktokWebhook,
  tiktokPendingAccess,
  tiktokMessagingEnabled,
  oauthAvailable,
  webhookFor,
  onBindingsChange,
}: TikTokChannelSectionProps) {
  const t = useTranslations("Channels");

  return (
    <ChannelCard
      title={t("tiktok.title")}
      icon="🎵"
      bindings={bindings}
      agentId={agentId}
      channelType="tiktok"
      pendingAccess={
        tiktokPendingAccess ||
        bindings.some((b) => isPendingChannelAccess(b.metadata))
      }
      tiktokMessagingEnabled={tiktokMessagingEnabled}
      oauthAvailable={oauthAvailable}
      webhookFor={webhookFor}
      onBindingsChange={onBindingsChange}
      guide={
        <TikTokChannelGuide
          tiktokWebhook={tiktokWebhook}
          tiktokPendingAccess={tiktokPendingAccess}
        />
      }
      banner={
        tiktokPendingAccess ? (
          <div className="px-5 py-3 text-xs text-foreground bg-surface-hover border-b border-border">
            {t("tiktok.pendingBanner")}
          </div>
        ) : undefined
      }
    />
  );
}
