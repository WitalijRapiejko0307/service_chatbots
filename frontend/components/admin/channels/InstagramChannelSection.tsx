"use client";

import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import type { ChannelBinding, ChannelConfig } from "@/lib/types/channel";
import { ChannelCard } from "./ChannelCard";
import { ChannelSettingsForm } from "./ChannelSettingsForm";
import { InstagramChannelGuide } from "./InstagramChannelGuide";

interface InstagramChannelSectionProps {
  agentId: string;
  bindings: ChannelBinding[];
  config: ChannelConfig | null;
  igWebhookUrl: string;
  webhookFor: (binding?: ChannelBinding) => string;
  onBindingsChange: () => void;
  onConfigUpdate: (config: ChannelConfig) => void;
}

export function InstagramChannelSection({
  agentId,
  bindings,
  config,
  igWebhookUrl,
  webhookFor,
  onBindingsChange,
  onConfigUpdate,
}: InstagramChannelSectionProps) {
  const t = useTranslations("Channels");

  return (
    <ChannelCard
      title={t("instagram.title")}
      icon="📷"
      bindings={bindings}
      agentId={agentId}
      channelType="instagram"
      oauthAvailable={config?.instagram_oauth_available === true}
      webhookFor={webhookFor}
      onBindingsChange={onBindingsChange}
      guide={
        <InstagramChannelGuide
          igWebhookUrl={igWebhookUrl}
          config={config}
          onConfigUpdate={onConfigUpdate}
        />
      }
      settingsForm={
        config ? (
          <ChannelSettingsForm
            title={t("instagram.title")}
            currentVerifyToken={config.instagram_verify_token}
            appSecretConfigured={config.instagram_app_secret_configured}
            verifyTokenHint={t("verifyTokenHint")}
            onSave={async (data) => {
              await api.updateInstagramSettings(data);
              const updated = await api.getChannelConfig();
              onConfigUpdate(updated);
            }}
          />
        ) : undefined
      }
    />
  );
}
